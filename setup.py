from setuptools import setup, Extension, find_packages
import os
import sys
import pybind11
import numpy as np

def get_include_paths():
    project_root = os.path.dirname(os.path.abspath(__file__))
    return [
        project_root,
        os.path.join(project_root, "mexc_protobuf"),
        pybind11.get_include(),
        "/opt/homebrew/include",
        os.path.join(sys.prefix, "include"),
        os.path.join(sys.prefix, "include", "google", "protobuf"),
        np.get_include(),
    ]
def get_library_dirs():
    return [
        os.path.join(sys.prefix, "lib"),
        "/opt/homebrew/lib",
    ]
proto_sources = [
    "mexc_protobuf/PushDataV3ApiWrapper.pb.cc",
    "mexc_protobuf/PrivateAccountV3Api.pb.cc",
    "mexc_protobuf/PublicAggreBookTickerV3Api.pb.cc",
    "mexc_protobuf/PublicBookTickerBatchV3Api.pb.cc",
    "mexc_protobuf/PublicIncreaseDepthsBatchV3Api.pb.cc",
    "mexc_protobuf/PublicMiniTickersV3Api.pb.cc",
    "mexc_protobuf/PrivateDealsV3Api.pb.cc",
    "mexc_protobuf/PublicAggreDealsV3Api.pb.cc",
    "mexc_protobuf/PublicIncreaseDepthsV3Api.pb.cc",
    "mexc_protobuf/PublicBookTickerV3Api.pb.cc",
    "mexc_protobuf/PublicMiniTickerV3Api.pb.cc",
    "mexc_protobuf/PrivateOrdersV3Api.pb.cc",
    "mexc_protobuf/PublicAggreDepthsV3Api.pb.cc",
    "mexc_protobuf/PublicDealsV3Api.pb.cc",
    "mexc_protobuf/PublicLimitDepthsV3Api.pb.cc",
    "mexc_protobuf/PublicSpotKlineV3Api.pb.cc",
]
proto_wrapper_file = "mexc_protobuf/mexc_proto_wrapper.cpp"
if os.path.exists(proto_wrapper_file):
    proto_sources.append(proto_wrapper_file)

proto_extension = Extension(
    name='proto_wrapper_mexc',
    sources=proto_sources,
    include_dirs=get_include_paths(),
    library_dirs=get_library_dirs(),
    libraries=["protobuf"],
    extra_compile_args=[
        "-std=c++17",
        "-O3",  
        "-Wall", 
    ],
    language="c++",
)

rsi_extension = Extension(
    name='rsi_calculator',
    sources=[
        'core/rsi.cpp',
    ],
    include_dirs=get_include_paths() + [
        np.get_include(),
        'core'  
    ],
    extra_compile_args=[
        "-std=c++17",
        "-O3",
        "-march=native",
        "-ffast-math",
    ],
    language="c++",
)

slope_extension = Extension(
    name='slope_calculator',
    sources=['core/slope_calculator.cpp'],
    include_dirs=get_include_paths() + [np.get_include()],
    extra_compile_args=[
        "-std=c++17",
        "-O3",
        "-mcpu=apple-m1",  
        "-ffast-math",
        "-flto"  
    ],
    language="c++",
)

order_flow_extension = Extension(
    name="order_flow",
    sources=["core/order_flow.cpp"],
    include_dirs=get_include_paths() + ['mexc_protobuf'],
    extra_compile_args=["-std=c++17", "-O3"],
    language="c++",
)
setup(
    name="bot",
    version="0.1.0",
    packages=find_packages(),
    ext_modules= [proto_extension, slope_extension, rsi_extension, order_flow_extension],
    python_requires=">=3.7",
    install_requires=[
        'pybind11>=2.6.0',
        'protobuf>=6.31.1',
        'numpy>=1.21.0',
        'cython>=0.29.0',
        'nlohmann-json>=3.10.0',  
        'pycurl>=7.45.1'          
    ]
)