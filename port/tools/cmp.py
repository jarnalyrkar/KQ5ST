import os, sys
a, b, t = sys.argv[1], sys.argv[2], sys.argv[3]
A = {int(f) for f in os.listdir(f'{a}/{t}') if f.isdigit()}
B = {int(f) for f in os.listdir(f'{b}/{t}') if f.isdigit()}
same = []; diff = []
for n in sorted(A & B):
    x = open(f'{a}/{t}/{n}', 'rb').read(); y = open(f'{b}/{t}/{n}', 'rb').read()
    (same if x == y else diff).append((n, len(x), len(y)))
print(f'{t}: common {len(A&B)}, identical {len(same)}, different {len(diff)}')
print('  only in DOS  :', sorted(A - B))
print('  only in Amiga:', sorted(B - A))
print('  different (n, dos, amiga):', diff)
