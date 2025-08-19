from dash import callback, Input, Output, State, ctx, html, no_update
import pickle
import pandas as pd
import plotly.express as px
import os, csv
from datetime import datetime, timezone
from flask import request
from helpers import nearest_neighbor_order, build_node_route, plot_graph, path_length, visited_path

@callback(
    Output("plot-order-cnt-daily", "figure"),
    Output("plot-operator-cnt-orders", "figure"),
    Input("date-picker", "start_date"),
    Input("date-picker", "end_date"),
)
def update_date_range(start_date, end_date):

    # ---- 1 ) Total orders per day bar plot

    co = pd.read_csv("Customer_Order.csv", sep=";")
    co["creationDate"] = pd.to_datetime(co["creationDate"])
    co_filtered = co.loc[(co["creationDate"] >= start_date) & (co["creationDate"] <= end_date), :].copy()
    co_filtered.rename(columns={"creationDate":"creationDateTime"}, inplace=True)
    co_filtered["creationDate"] = co_filtered["creationDateTime"].dt.date
    order_cnt_daily = co_filtered.groupby(["creationDate"])["orderNumber"].nunique().reset_index()
    
    fig = px.bar(order_cnt_daily, x="creationDate", y="orderNumber",
                 color_discrete_sequence=["#f28e2b"]
                 )
    fig.update_layout(
        margin=dict(l=60, r=15, t=10, b=60),   # left, right, top, bottom
        xaxis=dict(title="Date")
    )


    # ---- 2 ) operators bar plot

    co_filtered_by_op = co_filtered.groupby(["creationDate", "operator"])["orderNumber"].nunique().reset_index()
    # normalizing the work of operators by day
    co_filtered_by_op_normalized = co_filtered_by_op.pivot(index="creationDate",columns="operator").sum() / co_filtered_by_op.pivot(index="creationDate",columns="operator").count()
    co_filtered_by_op_normalized = (co_filtered_by_op_normalized
                                    .reset_index()
                                    .rename(columns={0:"avg orders per day"})
                                    .sort_values(by="avg orders per day", ascending=False)
                                    )
    # connvert Operator word to "Op_" for simplicity
    co_filtered_by_op_normalized["operator"] = "Op_" + co_filtered_by_op_normalized["operator"].str.split("_").str[1]
    # make the plot
    fig_op = px.bar(co_filtered_by_op_normalized, x="operator", y="avg orders per day", 
                    color_discrete_sequence=["#f28e2b"])
    # calculate the overall avg
    overall_avg = co_filtered_by_op_normalized["avg orders per day"].mean()
    # add horizontal line
    fig_op.add_hline(y=overall_avg, line_dash="dash", line_color="red",
                annotation_text="Overall Avg", annotation_position="top left")
    fig_op.update_layout(
        margin=dict(l=60, r=40, t=10, b=70),
        xaxis=dict(tickangle=45),
    )
    return fig, fig_op



@callback(
    Output("orders-dropdown", "options"),
    Output("operator-orders-info","children"),
    Input("plot-operator-cnt-orders", "clickData"),
    State("date-picker", "start_date"),
    State("date-picker", "end_date"),
    prevent_initial_call=True
)
def simulator(operator, start_date, end_date):
    # get the operator and convert the name from "Op_" to "operator_"
    operator = "Operator_" + operator['points'][0]['x'].split("_")[1]
    
    co = pd.read_csv("Customer_Order.csv", sep=";")
    co["creationDate"] = pd.to_datetime(co["creationDate"])
    co_filtered = co.loc[(co["creationDate"] >= start_date) & (co["creationDate"] <= end_date), :].copy()

    # All the Details below are for the operator that the user selected

    orders_handled_by_op = co_filtered.loc[co_filtered['operator'] == operator, "orderNumber"].unique()

    total_num_day_working = co_filtered.loc[co_filtered['operator'] == operator, "creationDate"].nunique()

    total_num_orders_handled_by_op = co_filtered.loc[co_filtered['operator'] == operator, "orderNumber"].nunique()

    total_num_SKU_in_each_order = co_filtered.groupby(["operator", "orderNumber"])["Reference"].nunique().reset_index()
    avg_num_SKU_in_orders_handled_by_op = total_num_SKU_in_each_order.loc[total_num_SKU_in_each_order["operator"]==operator, :]['Reference'].mean()

    operator_work_details = html.P([
        f"Operator ID: {operator.split('_')[1]}", html.Br(),
        f"Total Working Days: {total_num_day_working}", html.Br(),
        f"Total Handled Orders: {total_num_orders_handled_by_op}", html.Br(),
        f"Average SKU by Orders: {round(avg_num_SKU_in_orders_handled_by_op, 2)}"
    ])

    return orders_handled_by_op, operator_work_details

    
@callback(
    Output("warehouse", "figure"),
    Output("path-length", "children"),
    Input("orders-dropdown", "value"),
    Input("toggle-path-optimizer", "value"),
    prevent_initial_call=True
)
def order_details(orderID, toggle_path_optimizer):

    if not orderID:
        return no_update, no_update
    
    # Load warehouse plot
    with open("warehouse_graph.pkl", "rb") as f:
        G = pickle.load(f)

    # 1) Build positions from node attributes (x,y) so the plot uses floor-plan coordinates.
    pos = {n: (G.nodes[n]['x'], G.nodes[n]['y']) for n in G.nodes()}

    # connecting Picking_Wave data to customer orders data and some preprocessing
    co = pd.read_csv("Customer_Order.csv", sep=";")
    pw = pd.read_csv("Picking_Wave_filtered.csv")
    co.rename(columns={'Reference':'reference'}, inplace=True)

    co_order_filtered = co.loc[co["orderNumber"]== orderID, ["orderNumber", "orderToCollect", "waveNumber", "operator", "reference", "quantity (units)"]]
    co_pw_merged = pd.merge(left=pw[["waveNumber","locations", 'reference']], right=co_order_filtered, on=['waveNumber', 'reference'], how="right")
    # co_order_filtered
    co_pw_merged = co_pw_merged.groupby(["waveNumber", "locations", "reference", "orderNumber", "operator", "orderToCollect"])['quantity (units)'].max().reset_index()

    # load base figure
    fig = plot_graph(G, pos)
    
    paths = {}
    for op in co_pw_merged['operator'].unique():
        co_pw_merged_filtered_by_op = co_pw_merged.loc[co_pw_merged['operator']==op, :]
        path = co_pw_merged_filtered_by_op.sort_values('orderToCollect')['locations']
        paths[op] = [p.strip() for p in path.values]

    if not toggle_path_optimizer:
        for i ,(_, path) in enumerate(paths.items()):
            path.insert(0, 'Start')
            route_nodes = build_node_route(G, path + ["Start"])
            # add to figure
            fig = visited_path(fig, pos, route_nodes, i)
    else:
        for i ,(_, path) in enumerate(paths.items()):
            visit_order = nearest_neighbor_order(G, path, start="Start")
            route_nodes = build_node_route(G, visit_order + ["Start"])
            # add to figure
            fig = visited_path(fig, pos, route_nodes, i)

    if paths:
        length = path_length(route_nodes, G)
        path_string = html.P(f"Total path to pick this order: {length} meter by {i+1} Operator(s)", style={"font-size":"18px"})
    
        return fig, path_string
    else:
        return fig, html.P(f"For this Order there is no data available. Please select another Order!", style={"font-size":"18px"})


@callback(Output("visit-logger", "children"), 
          Input("url", "pathname"))
def log_visit(_pathname):
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or request.headers.get("X-Real-IP", "")
          or request.remote_addr)
    row = [
        datetime.now(timezone.utc).isoformat(),
        ip[:-3]+"xxx",
        request.path,
        request.referrer,
        # request.headers.get("User-Agent", "")
    ]
    with open("visits.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
    return ""