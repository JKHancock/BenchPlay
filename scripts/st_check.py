import json, os, struct, sys
d = sys.argv[1] if len(sys.argv) > 1 else '/root/.cache/huggingface/DeepSeek-V4-Flash-NVFP4'
bad = 0
for f in sorted(os.listdir(d)):
    if not f.endswith('.safetensors'):
        continue
    p = os.path.join(d, f)
    n = os.path.getsize(p)
    with open(p, 'rb') as fh:
        hb = fh.read(8)
        if len(hb) < 8:
            print('EMPTY', f); bad += 1; continue
        hl = struct.unpack('<Q', hb)[0]
        if 8 + hl > n:
            print('HDR-TRUNC', f, n, hl); bad += 1; continue
        meta = json.loads(fh.read(hl))
        cov = max((v["data_offsets"][1] for k, v in meta.items() if k != "__metadata__"), default=0)
        if 8 + hl + cov != n:
            print('NOT-COVERED', f, 'file=', n, 'header+cover=', 8 + hl + cov); bad += 1
print('CHECK-DONE bad=', bad)
