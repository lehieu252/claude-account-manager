#!/bin/bash
# Test end-to-end bằng account GIẢ trong thư mục tạm. Dùng: bash tests/e2e.sh <thư-mục-tạm> scripts/claude_acct.py
S="$1"; SCRIPT="$2"; rm -rf "$S"; mkdir -p "$S/cfg"
run(){ echo "\$ acct $*"; CLAUDE_CONFIG_DIR="$S/cfg" CLAUDE_ACCT_HOME="$S/store" CLAUDE_ACCT_KEYCHAIN_SERVICE=claude-acct-TEST python3 -I "$SCRIPT" "$@"; echo "[exit $?]"; }
login(){ python3 -I - "$S/cfg" "$1" "$2" <<'EOF'
import json,sys,time
d,who,tok=sys.argv[1:]
json.dump({"claudeAiOauth":{"accessToken":tok,"refreshToken":"r-"+tok,"expiresAt":int(time.time()*1000)-1,"subscriptionType":"max"}},open(d+"/.credentials.json","w"))
try: g=json.load(open(d+"/.claude.json"))
except Exception: g={"other":"keep-me"}
g["oauthAccount"]={"accountUuid":"u-"+who,"organizationUuid":"o1","emailAddress":who+"@x.com","organizationName":"Org"}
json.dump(g,open(d+"/.claude.json","w"))
EOF
}
live(){ python3 -I -c "import json;c=json.load(open('$S/cfg/.credentials.json'));g=json.load(open('$S/cfg/.claude.json'));print('LIVE =',c['claudeAiOauth']['accessToken'],g['oauthAccount']['emailAddress'],'other=',g.get('other'))"; }
for BACKEND in keychain file; do
 echo "=========== store backend: $BACKEND"; rm -rf "$S/store" "$S/cfg"; mkdir -p "$S/cfg"
 if [ $BACKEND = file ]; then export CLAUDE_ACCT_BACKEND=file; fi
 run list
 login A tokA1; run save a
 run save a2
 login B tokB1; run switch a
 run save b
 run save a
 login B tokB2; run switch a; live
 run list
 run switch b; live
 run switch b
 run switch zzz
 run remove a; run list
 run remove b
 unset CLAUDE_ACCT_BACKEND
done
echo "== keychain item test còn sót: $(security dump-keychain 2>/dev/null | grep -c claude-acct-TEST)"
