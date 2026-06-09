import sys, json
sys.path.insert(0, 'src')
from ctxorg.server import _rl_policy, _rl_take

cfg = {}
row = _rl_policy(cfg, 'POST', '/api/signup')
print('Policy:', row)

actor, scope, cap = 'ip:127.0.0.1', 'signup_post', 5
for i in range(8):
    wait = _rl_take(actor, scope, cap)
    print(f'  req {i+1}: wait={wait:.2f}s')
