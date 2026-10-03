import socket
import struct
import time

s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(3))
log = open('/tmp/sse8000.log', 'a', buffering=1)
NAMES = [(0x02, 'SYN'), (0x01, 'FIN'), (0x04, 'RST')]

while True:
    pkt, _ = s.recvfrom(65535)
    if len(pkt) < 54:
        continue
    if struct.unpack('!H', pkt[12:14])[0] != 0x0800:
        continue  # 仅IPv4
    ihl = (pkt[14] & 0xF) * 4
    if pkt[14 + 9] != 6:
        continue  # 仅TCP
    t = 14 + ihl
    sport, dport = struct.unpack('!HH', pkt[t:t + 4])
    if 8000 not in (sport, dport):
        continue
    flags = pkt[t + 13]
    hits = [n for b, n in NAMES if flags & b]
    if not hits:
        continue
    src = '.'.join(map(str, pkt[26:30]))
    dst = '.'.join(map(str, pkt[30:34]))
    print(time.strftime('%F %T.%f')[:-3],
          f"{src}:{sport} > {dst}:{dport} [{'+'.join(hits)}]", file=log)
