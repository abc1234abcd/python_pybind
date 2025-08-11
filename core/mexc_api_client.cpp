#include <iostream>
#include <string>
#include <map>
#include <chrono>
#include <vector>
#include <algorithm>
#include <openssl/hmac.h>
#include <openssl/sha.h>
#include <curl/curl.h>
#include <nlohmann/json.hpp>
#include <atomic>
#include <mutex>
#include <memory>
#include <iomanip>
#include <sstream>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/chrono.h>

using json = nlohmann::json;
namespace py = pybind11;

// Low-latency connection pool
class ConnectionPool {
private:
    std::vector<CURL*> connections;
    std::mutex pool_mutex;
    size_t pool_size;
    
public:
    ConnectionPool(size_t size) : pool_size(size) {
        for (size_t i = 0; i < pool_size; ++i) {
            connections.push_back(curl_easy_init());
        }
    }
    
    CURL* acquire() {
        std::lock_guard<std::mutex> lock(pool_mutex);
        if (connections.empty()) {
            return curl_easy_init(); // Fallback if pool is empty
        }
        CURL* conn = connections.back();
        connections.pop_back();
        return conn;
    }
    
    void release(CURL* conn) {
        std::lock_guard<std::mutex> lock(pool_mutex);
        if (connections.size() < pool_size) {
            curl_easy_reset(conn);
            connections.push_back(conn);
        } else {
            curl_easy_cleanup(conn);
        }
    }
    
    ~ConnectionPool() {
        for (CURL* conn : connections) {
            curl_easy_cleanup(conn);
        }
    }
};

// Write callback for CURL
static size_t WriteCallback(void* contents, size_t size, size_t nmemb, std::string* s) {
    size_t newLength = size * nmemb;
    try {
        s->append((char*)contents, newLength);
        return newLength;
    } catch(std::bad_alloc &e) {
        return 0;
    }
}

class MexcApiClient {
private:
    std::string api_key;
    std::string api_secret;
    const std::string api_base_url = "https://api.mexc.com";
    std::unique_ptr<ConnectionPool> connection_pool;
    std::chrono::milliseconds timeout;
    
    // Thread-safe timestamp cache
    std::atomic<uint64_t> last_timestamp{0};
    std::mutex timestamp_mutex;
    
    std::string generate_signature(const std::map<std::string, std::string>& params) {
        std::string query_string;
        for (const auto& [key, value] : params) {
            if (!query_string.empty()) query_string += "&";
            query_string += key + "=" + value;
        }
        
        unsigned char digest[SHA256_DIGEST_LENGTH];
        HMAC_CTX* hmac_ctx = HMAC_CTX_new();
        HMAC_Init_ex(hmac_ctx, api_secret.data(), api_secret.size(), EVP_sha256(), NULL);
        HMAC_Update(hmac_ctx, (unsigned char*)query_string.data(), query_string.size());
        HMAC_Final(hmac_ctx, digest, NULL);
        HMAC_CTX_free(hmac_ctx);
        
        std::stringstream ss;
        for (unsigned char i : digest) {
            ss << std::hex << std::setw(2) << std::setfill('0') << (int)i;
        }
        
        return ss.str();
    }
    
    uint64_t get_current_timestamp() {
        // Cache timestamp to avoid frequent system calls
        uint64_t now = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        
        uint64_t last = last_timestamp.load(std::memory_order_relaxed);
        if (now > last) {
            std::lock_guard<std::mutex> lock(timestamp_mutex);
            last = last_timestamp.load(std::memory_order_relaxed);
            if (now > last) {
                last_timestamp.store(now, std::memory_order_relaxed);
                return now;
            }
        }
        return last;
    }
    
    json make_request(const std::string& method, const std::string& path, 
                     const std::map<std::string, std::string>& params = {}) {
        CURL* curl = connection_pool->acquire();
        std::string read_buffer;
        struct curl_slist* headers = nullptr;
        json result;

        try {
            // Prepare URL
            std::string url = api_base_url + path;
            
            // Prepare headers
            headers = curl_slist_append(headers, ("X-MEXC-APIKEY: " + api_key).c_str());
            headers = curl_slist_append(headers, "Content-Type: application/json");
            
            // Prepare query parameters
            std::string query_string;
            for (const auto& [key, value] : params) {
                if (!query_string.empty()) query_string += "&";
                query_string += key + "=" + value;
            }
            
            // Set CURL options
            curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
            curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, method.c_str());
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
            curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
            curl_easy_setopt(curl, CURLOPT_WRITEDATA, &read_buffer);
            curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, timeout.count());
            curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
            
            if (!query_string.empty()) {
                if (method == "GET" || method == "DELETE") {
                    curl_easy_setopt(curl, CURLOPT_URL, (url + "?" + query_string).c_str());
                } else {
                    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, query_string.c_str());
                }
            }
            
            // Execute request
            CURLcode res = curl_easy_perform(curl);
            
            if (res != CURLE_OK) {
                throw std::runtime_error("CURL error: " + std::string(curl_easy_strerror(res)));
            }
            
            // Parse JSON response
            result = json::parse(read_buffer);
        } catch (...) {
            if (headers) curl_slist_free_all(headers);
            connection_pool->release(curl);
            throw;
        }
        
        if (headers) curl_slist_free_all(headers);
        connection_pool->release(curl);
        return result;
    }
    
    std::map<std::string, std::string> get_signed_params(std::map<std::string, std::string> params) {
        params["timestamp"] = std::to_string(get_current_timestamp());
        std::string signature = generate_signature(params);
        params["signature"] = signature;
        return params;
    }
    
public:
    MexcApiClient(const std::string& key, const std::string& secret, 
                 std::chrono::milliseconds timeout_ms = std::chrono::milliseconds(2000),
                 size_t pool_size = 20)
        : api_key(key), api_secret(secret), timeout(timeout_ms) {
        curl_global_init(CURL_GLOBAL_DEFAULT);
        connection_pool = std::make_unique<ConnectionPool>(pool_size);
    }
    
    ~MexcApiClient() {
        curl_global_cleanup();
    }
    
    std::string generate_listen_key() {
        auto params = get_signed_params({});
        json response = make_request("POST", "/api/v3/userDataStream", params);
        return response["listenKey"];
    }
    
    bool put_listen_key(const std::string& listen_key) {
        auto params = get_signed_params({{"listenKey", listen_key}});
        json response = make_request("PUT", "/api/v3/userDataStream", params);
        return response["listenKey"] == listen_key;
    }
    
    bool delete_listen_key(const std::string& listen_key) {
        auto params = get_signed_params({{"listenKey", listen_key}});
        json response = make_request("DELETE", "/api/v3/userDataStream", params);
        return response["listenKey"] == listen_key;
    }
    
    json submit_order(const std::map<std::string, std::string>& order_params) {
        auto params = get_signed_params(order_params);
        return make_request("POST", "/api/v3/order", params);
    }
    
    json cancel_order(const std::string& symbol, 
                     const std::optional<std::string>& order_id = std::nullopt,
                     const std::optional<std::string>& orig_client_order_id = std::nullopt,
                     const std::optional<std::string>& new_client_order_id = std::nullopt,
                     const std::optional<int>& recv_window = std::nullopt) {
        std::map<std::string, std::string> params = {
            {"symbol", symbol},
            {"timestamp", std::to_string(get_current_timestamp())}
        };
        
        if (order_id) params["orderId"] = *order_id;
        if (orig_client_order_id) params["origClientOrderId"] = *orig_client_order_id;
        if (new_client_order_id) params["newClientOrderId"] = *new_client_order_id;
        if (recv_window) params["recvWindow"] = std::to_string(*recv_window);
        
        auto signed_params = get_signed_params(params);
        return make_request("POST", "/api/v3/order/test", signed_params);
    }
    
    json cancel_all_orders(const std::string& symbol, 
                          const std::optional<int>& recv_window = std::nullopt) {
        std::map<std::string, std::string> params = {
            {"symbol", symbol},
            {"timestamp", std::to_string(get_current_timestamp())}
        };
        
        if (recv_window) params["recvWindow"] = std::to_string(*recv_window);
        
        auto signed_params = get_signed_params(params);
        return make_request("DELETE", "/api/v3/openOrders", signed_params);
    }
    
    json get_order_status(const std::string& order_id, const std::string& symbol = "SOLUSDT") {
        std::map<std::string, std::string> params = {
            {"orderId", order_id},
            {"symbol", symbol},
            {"timestamp", std::to_string(get_current_timestamp())}
        };
        
        auto signed_params = get_signed_params(params);
        return make_request("GET", "/api/v3/order", signed_params);
    }
    
    double get_account_balance() {
        std::map<std::string, std::string> params = {
            {"timestamp", std::to_string(get_current_timestamp())}
        };
        
        auto signed_params = get_signed_params(params);
        json response = make_request("GET", "/api/v3/account", signed_params);
        
        for (const auto& balance : response["balances"]) {
            if (balance["asset"] == "USDT") {
                return std::stod(balance["free"].get<std::string>()) + 
                       std::stod(balance["locked"].get<std::string>());
            }
        }
        
        return 0.0;
    }
    
    json get_exchange_info(const std::string& symbol) {
        std::map<std::string, std::string> params = {{"symbol", symbol}};
        return make_request("GET", "/api/v3/exchangeInfo", params);
    }
    
    json get_default_symbols() {
        auto params = get_signed_params({});
        return make_request("GET", "/api/v3/selfSymbols", params);
    }
};

PYBIND11_MODULE(mexc_api, m) {
    py::class_<MexcApiClient>(m, "MexcApiClient")
        .def(py::init<const std::string&, const std::string&, 
                      std::chrono::milliseconds, size_t>(),
             py::arg("api_key"), py::arg("api_secret"),
             py::arg("timeout") = std::chrono::milliseconds(2000),
             py::arg("pool_size") = 20)
        .def("generate_listen_key", &MexcApiClient::generate_listen_key)
        .def("put_listen_key", &MexcApiClient::put_listen_key)
        .def("delete_listen_key", &MexcApiClient::delete_listen_key)
        .def("submit_order", &MexcApiClient::submit_order)
        .def("cancel_order", &MexcApiClient::cancel_order,
             py::arg("symbol"),
             py::arg("order_id") = py::none(),
             py::arg("orig_client_order_id") = py::none(),
             py::arg("new_client_order_id") = py::none(),
             py::arg("recv_window") = py::none())
        .def("cancel_all_orders", &MexcApiClient::cancel_all_orders,
             py::arg("symbol"), py::arg("recv_window") = py::none())
        .def("get_order_status", &MexcApiClient::get_order_status,
             py::arg("order_id"), py::arg("symbol") = "SOLUSDT")
        .def("get_account_balance", &MexcApiClient::get_account_balance)
        .def("get_exchange_info", &MexcApiClient::get_exchange_info)
        .def("get_default_symbols", &MexcApiClient::get_default_symbols);
}