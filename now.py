import struct

record_size = 20  # replace with actual size of one record
with open("CLX5_mbo(2).dbn", "rb") as f:
    header = f.read(32)  # skip header if needed
    for _ in range(20):
        record = f.read(record_size)
        if not record:
            break
        fields = struct.unpack("!I Q f f", record)  # example
        print(fields)


        

