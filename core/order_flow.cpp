#include <vector>
#include <string>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "mexc_protobuf/PublicAggreDealsV3Api.pb.h"

namespace py = pybind11;

struct OrderFlowResult {
    double bid_volume;
    double ask_volume;
    double net_flow;
    double price_delta;
    double normalized_net_flow;

};

OrderFlowResult compute_order_flow(const std::vector<PublicAggreDealsV3ApiItem>& deals) {
    double bid_volume = 0.0;
    double ask_volume = 0.0;
    double price_delta = 0.0;

    if (!deals.empty()){
        double first_price = std::stod(deals.front().price());
        double last_price = std::stod(deals.back().price());
        price_delta = last_price - first_price;
    }

    if (!deals.empty()){
        for (const auto& deal : deals) {
            double quantity = std::stod(deal.quantity());
            int trade_type = deal.tradetype();  

            if (trade_type == 1) {  
                bid_volume += quantity;
            } else if (trade_type == 2) {  
                ask_volume += quantity;
            }
        }
    }
    return {
        bid_volume,
        ask_volume,
        bid_volume - ask_volume,
        price_delta,
        (bid_volume - ask_volume) /(bid_volume + ask_volume),
    };
}

// PyBind11 module definition
PYBIND11_MODULE(order_flow, m) {
    py::class_<OrderFlowResult>(m, "OrderFlowResult")
        .def_readonly("bid_volume", &OrderFlowResult::bid_volume)
        .def_readonly("ask_volume", &OrderFlowResult::ask_volume)
        .def_readonly("net_flow", &OrderFlowResult::net_flow)
        .def_readonly("price_delta", &OrderFlowResult::price_delta)
        .def_readonly("normalized_net_flow", &OrderFlowResult::normalized_net_flow);

    m.def("compute_order_flow", &compute_order_flow, "Computes order flow from a list of AggreDealItem objects");
}