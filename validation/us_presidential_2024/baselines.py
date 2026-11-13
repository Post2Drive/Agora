import csv, statistics as st, math
D="/tmp/claude-0/elec/"
def read(p):
    with open(p,encoding="utf-8") as f: return list(csv.DictReader(f))
# ---- 2020 and 2024 (state_name, county_fips, votes_dem, votes_gop)
def by_state_new(rows, dem, gop):
    out={}
    for r in rows:
        s=r["state_name"]; d=float(r[dem]); g=float(r[gop])
        out.setdefault(s,[0.0,0.0]); out[s][0]+=d; out[s][1]+=g
    return {s:(d/(d+g)) for s,(d,g) in out.items() if d+g>0}
r24=read(D+"2024_US_County_Level_Presidential_Results.csv")
r20=read(D+"2020_US_County_Level_Presidential_Results.csv")
print("2020 cols:", list(r20[0].keys())[:8])
s24=by_state_new(r24,"votes_dem","votes_gop")
s20=by_state_new(r20,"votes_dem","votes_gop")
# ---- 2008-2016 (fips only): map fips prefix -> state name via 2024 file
fips2state={}
for r in r24:
    fips2state.setdefault(r["county_fips"][:2], r["state_name"])
old=read(D+"US_County_Level_Presidential_Results_08-16.csv")
hist={}
for y in (2008,2012,2016):
    agg={}
    for r in old:
        fp=str(r["fips_code"]).zfill(5)[:2]
        s=fips2state.get(fp)
        if not s: continue
        d=float(r[f"dem_{y}"] or 0); g=float(r[f"gop_{y}"] or 0)
        agg.setdefault(s,[0.0,0.0]); agg[s][0]+=d; agg[s][1]+=g
    hist[y]={s:d/(d+g) for s,(d,g) in agg.items() if d+g>0}
hist[2020]=s20
years=[2008,2012,2016,2020]
states=sorted(set(s24)&set(hist[2008])&set(hist[2016]))
print("states scored:", len(states))
# national two-party sanity (2024 file totals)
D24=sum(float(r["votes_dem"]) for r in r24); G24=sum(float(r["votes_gop"]) for r in r24)
print(f"2024 national two-party Dem share from file: {D24/(D24+G24):.4f}  (dem {D24:,.0f}, gop {G24:,.0f})")
def trend(s):
    xs=years; ys=[hist[y][s] for y in years]
    mx=sum(xs)/4; my=sum(ys)/4
    b=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sum((x-mx)**2 for x in xs)
    return my+b*(2024-mx)
preds={
 "last value (2020)": {s:hist[2020][s] for s in states},
 "mean 2008-2020": {s:sum(hist[y][s] for y in years)/4 for s in states},
 "linear trend 2008-2020": {s:trend(s) for s in states},
}
for name,p in preds.items():
    e=[p[s]-s24[s] for s in states]
    mae=sum(abs(x) for x in e)/len(e); rmse=math.sqrt(sum(x*x for x in e)/len(e))
    print(f"{name:26s} MAE={mae*100:5.2f} pts  RMSE={rmse*100:5.2f} pts  bias={sum(e)/len(e)*100:+.2f}")
