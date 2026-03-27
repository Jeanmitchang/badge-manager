#!/usr/bin/env python3
"""server_v2.py — Badge Manager v2.1"""
import asyncio,base64,hashlib,hmac,json,os,subprocess,time,psutil
from datetime import datetime,timedelta
from pathlib import Path
from fastapi import FastAPI,HTTPException,Depends,Request,Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from pydantic import BaseModel,Field,field_validator
import database as D

BASE_DIR=Path(__file__).parent
CONFIG={"vigik_exe":os.environ.get("VIGIK_EXE",str(BASE_DIR/"vigik_loader_cli.exe")),"cert_file":os.environ.get("VIGIK_CERT",str(BASE_DIR/"cert.txt")),"mct_output_dir":os.environ.get("VIGIK_MCT",str(BASE_DIR/"mct_output")),"host":os.environ.get("VIGIK_HOST","0.0.0.0"),"port":int(os.environ.get("VIGIK_PORT","8766")),"jwt_secret":os.environ.get("VIGIK_JWT_SECRET","change-this-secret-v2"),"ssl_cert":os.environ.get("VIGIK_SSL_CERT",str(BASE_DIR/"budgie-server.tail609373.ts.net.crt")),"ssl_key":os.environ.get("VIGIK_SSL_KEY",str(BASE_DIR/"budgie-server.tail609373.ts.net.key"))}

def _b64url(d):return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
def jwt_sign(p):
    h=_b64url(json.dumps({"alg":"HS256","typ":"JWT"}).encode())
    b=_b64url(json.dumps(p).encode())
    s=_b64url(hmac.new(CONFIG["jwt_secret"].encode(),f"{h}.{b}".encode(),hashlib.sha256).digest())
    return f"{h}.{b}.{s}"
def jwt_verify(token):
    try:
        h,b,s=token.split(".")
        e=_b64url(hmac.new(CONFIG["jwt_secret"].encode(),f"{h}.{b}".encode(),hashlib.sha256).digest())
        if not hmac.compare_digest(s,e):raise ValueError("sig")
        p=json.loads(base64.urlsafe_b64decode(b+"=="))
        if p.get("exp",0)<time.time():raise ValueError("exp")
        return p
    except Exception as ex:raise HTTPException(401,f"Token invalide: {ex}")

bearer=HTTPBearer()
def require_auth(creds:HTTPAuthorizationCredentials=Depends(bearer)):
    p=jwt_verify(creds.credentials)
    u=D.get_user_by_id(p["sub"])
    if not u:raise HTTPException(401,"Compte introuvable")
    if not u["is_active"] or u["is_deleted"]:raise HTTPException(403,"ACCOUNT_BLOCKED")
    return p
def require_role(*roles):
    def dep(p=Depends(require_auth)):
        if p.get("role") not in roles:raise HTTPException(403,"Accès refusé")
        return p
    return dep
def get_ip(r:Request):return r.client.host if r.client else "unknown"

def get_ua(r:Request) -> tuple[str,str]:
    """Retourne (user_agent, device)."""
    ua = r.headers.get("user-agent","")
    # Détection simple du type de périphérique
    ua_lower = ua.lower()
    if any(x in ua_lower for x in ["mobile","android","iphone","ipad"]):
        device = "mobile"
    elif any(x in ua_lower for x in ["tablet"]):
        device = "tablet"
    else:
        device = "desktop"
    return ua[:200], device

def migrate_db():
    """Ajoute les colonnes manquantes si upgrade depuis ancienne version."""
    with D.db() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(activity_log)").fetchall()]
        if "user_agent" not in cols:
            conn.execute("ALTER TABLE activity_log ADD COLUMN user_agent TEXT")
        if "device" not in cols:
            conn.execute("ALTER TABLE activity_log ADD COLUMN device TEXT")

def validate_uid(uid:str):
    uid=uid.strip().upper()
    if len(uid)!=8:return False,"UID doit faire 8 caractères hexadécimaux"
    try:b=bytes.fromhex(uid)
    except ValueError:return False,"UID contient des caractères non hexadécimaux"
    if uid in("00000000","FFFFFFFF"):return False,"UID invalide (valeur réservée)"
    return True,uid

_wine_sem=asyncio.Semaphore(1);MAX_QUEUE=5;_queue_count=0

class LoginReq(BaseModel):login:str=Field(...,min_length=1,max_length=50);password:str=Field(...,min_length=1,max_length=14)
class ChangePwdReq(BaseModel):current_password:str=Field(...,min_length=1);new_password:str=Field(...,min_length=6,max_length=14)
class CreateAdminReq(BaseModel):login:str=Field(...,min_length=2,max_length=50,pattern=r'^[\w.\-]+$');password:str=Field(...,min_length=6,max_length=14);jwt_ttl_hours:int=Field(default=24,ge=1);group_limit:int=Field(default=0,ge=0)
class CreateUserReq(BaseModel):login:str=Field(...,min_length=2,max_length=50,pattern=r'^[\w.\-]+$');password:str=Field(...,min_length=6,max_length=14);admin_id:str|None=None;group_id:str|None=None;badge_quota:int=Field(default=5,ge=1,le=100);jwt_ttl_hours:int=Field(default=24,ge=1);notify_admin:bool=True
class UpdateUserReq(BaseModel):badge_quota:int|None=Field(default=None,ge=1,le=100);jwt_ttl_hours:int|None=None;is_active:int|None=None;group_id:str|None=None;admin_id:str|None=None
class CreateGroupReq(BaseModel):name:str=Field(...,min_length=1,max_length=50);color:str=Field(default="#8b5cf6");admin_id:str|None=None
class MoveUserGroupReq(BaseModel):user_id:str;group_id:str;notify:bool=True
class UIDValidator(BaseModel):
    uid:str=Field(...,min_length=8,max_length=8)
    @field_validator('uid')
    @classmethod
    def ck(cls,v):
        ok,msg=validate_uid(v)
        if not ok:raise ValueError(msg)
        return msg
class CreateBadgeReq(UIDValidator):name:str=Field(...,min_length=1,max_length=50);icon:str=Field(default="🔑")
class UpdateBadgeReq(BaseModel):
    name:str|None=Field(default=None,min_length=1,max_length=50);icon:str|None=None;uid:str|None=Field(default=None,min_length=8,max_length=8)
    @field_validator('uid')
    @classmethod
    def ck(cls,v):
        if v is None:return v
        ok,msg=validate_uid(v)
        if not ok:raise ValueError(msg)
        return msg
class StockBadgeReq(UIDValidator):name:str=Field(...,min_length=1,max_length=50);icon:str=Field(default="🔑")
class AttributeStockReq(BaseModel):badge_id:str;attributed_to:str
class RequestReq(BaseModel):type:str=Field(...,pattern=r'^(badge_quota|mct_rallonge|group_change|delete_user)$');motif:str|None=Field(default=None,max_length=280);group_to:str|None=None;target_id:str|None=None
class SendMsgReq(BaseModel):to_id:str;content:str=Field(...,min_length=1,max_length=280)
class ConfigUpdateReq(BaseModel):badge_quota_default:int|None=None;mct_daily_limit:int|None=None;jwt_ttl_hours_default:int|None=None;vigik_duration_hours:int|None=None;disk_alert_threshold_pct:int|None=None
class DispatchReq(BaseModel):
    type:str=Field(...,pattern=r'^(group_to_admin|user_to_group|user_to_admin)$')
    group_id:str|None=None
    admin_id:str|None=None
    user_id:str|None=None

app=FastAPI(title="Badge Manager v2",docs_url=None,redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

@app.on_event("startup")
async def startup():
    D.init_db();D.init_default_config()
    migrate_db()
    asyncio.create_task(_cleanup_loop());asyncio.create_task(_watchdog_loop())

@app.get("/api/me")
async def me(p=Depends(require_auth)):
    u=D.get_user_by_id(p["sub"])
    return{"login":u["login"],"role":u["role"],"must_change_pwd":bool(u["must_change_pwd"]),"is_active":bool(u["is_active"])}

@app.post("/api/login")
async def login(req:LoginReq,request:Request):
    u=D.get_user_by_login(req.login);ip=get_ip(request);ua,dev=get_ua(request)
    if not u or not D.check_pwd(req.password,u["pwd_hash"]):
        D.log_event("connexion_echec",user_login=req.login,ip=ip,user_agent=ua,device=dev)
        raise HTTPException(401,"Identifiant ou mot de passe incorrect")
    if not u["is_active"]:raise HTTPException(403,"ACCOUNT_BLOCKED")
    ttl=u["jwt_ttl_hours"]
    token=jwt_sign({"sub":u["id"],"login":u["login"],"role":u["role"],"iat":int(time.time()),"exp":int(time.time())+ttl*3600})
    D.log_event("connexion_ok",user_id=u["id"],user_login=u["login"],role=u["role"],ip=ip,user_agent=ua,device=dev)
    return{"token":token,"role":u["role"],"login":u["login"],"must_change_pwd":bool(u["must_change_pwd"]),"ttl_hours":ttl}

@app.post("/api/change-password")
async def change_pwd(req:ChangePwdReq,p=Depends(require_auth)):
    u=D.get_user_by_id(p["sub"])
    if not D.check_pwd(req.current_password,u["pwd_hash"]):raise HTTPException(400,"Mot de passe actuel incorrect")
    err=D.validate_pwd(req.new_password)
    if err:raise HTTPException(400,err)
    D.update_user(u["id"],pwd_hash=D.hash_pwd(req.new_password),must_change_pwd=0)
    D.log_event("password_changed",user_id=u["id"],user_login=u["login"])
    return{"ok":True,"redirect_login":True}

@app.get("/api/admins")
async def list_admins(p=Depends(require_role("superadmin"))):
    return[{**{k:v for k,v in a.items() if k!="pwd_hash"},"group_count":D.count_admin_groups(a["id"]),"user_count":len(D.get_users_by_admin(a["id"]))} for a in D.get_all_admins()]

@app.post("/api/admins",status_code=201)
async def create_admin(req:CreateAdminReq,p=Depends(require_role("superadmin"))):
    if D.get_user_by_login(req.login):raise HTTPException(409,f"Identifiant '{req.login}' déjà utilisé")
    err=D.validate_pwd(req.password)
    if err:raise HTTPException(400,err)
    a=D.create_user(login=req.login,password=req.password,role="admin",jwt_ttl_hours=req.jwt_ttl_hours,must_change_pwd=1)
    if req.group_limit>0:D.set_config(f"admin_group_limit_{a['id']}",str(req.group_limit))
    D.log_event("user_created",user_id=a["id"],user_login=a["login"],role="admin")
    return{k:v for k,v in a.items() if k!="pwd_hash"}

@app.patch("/api/admins/{aid}")
async def update_admin(aid:str,req:UpdateUserReq,p=Depends(require_role("superadmin"))):
    a=D.get_user_by_id(aid)
    if not a or a["role"]!="admin":raise HTTPException(404)
    ups={}
    if req.jwt_ttl_hours is not None:ups["jwt_ttl_hours"]=req.jwt_ttl_hours
    if req.is_active is not None:ups["is_active"]=req.is_active
    D.update_user(aid,**ups);return{"ok":True}

@app.delete("/api/admins/{aid}",status_code=204)
async def delete_admin(aid:str,p=Depends(require_role("superadmin"))):
    a=D.get_user_by_id(aid)
    if not a or a["role"]!="admin":raise HTTPException(404)
    D.soft_delete_user(aid,p["sub"]);return Response(status_code=204)

@app.post("/api/admins/{aid}/reset-password")
async def reset_admin_pwd(aid:str,body:dict,p=Depends(require_role("superadmin"))):
    err=D.validate_pwd(body.get("password",""))
    if err:raise HTTPException(400,err)
    a=D.get_user_by_id(aid)
    if not a:raise HTTPException(404)
    D.update_user(aid,pwd_hash=D.hash_pwd(body["password"]),must_change_pwd=1)
    return{"ok":True}

@app.get("/api/users")
async def list_users(p=Depends(require_auth)):
    role=p["role"]
    if role=="superadmin":us=D.get_all_users(include_deleted=True)
    elif role=="admin":us=D.get_users_by_admin(p["sub"])
    else:raise HTTPException(403)
    return[{**{k:v for k,v in u.items() if k!="pwd_hash"},"badges_count":D.count_user_badges(u["id"]),"mct_used":D.count_mct_last_24h(u["id"])} for u in us]

@app.post("/api/users",status_code=201)
async def create_user(req:CreateUserReq,p=Depends(require_auth)):
    if p["role"]=="user":raise HTTPException(403)
    if D.get_user_by_login(req.login):raise HTTPException(409,f"Identifiant '{req.login}' déjà utilisé")
    err=D.validate_pwd(req.password)
    if err:raise HTTPException(400,err)
    admin_id=req.admin_id if p["role"]=="superadmin" else p["sub"]
    gid=req.group_id
    if p["role"]=="admin" and gid:
        g=D.get_group(gid)
        if not g or g["admin_id"]!=p["sub"]:raise HTTPException(403,"Groupe non autorisé")
    u=D.create_user(login=req.login,password=req.password,role="user",admin_id=admin_id,group_id=gid,badge_quota=req.badge_quota,jwt_ttl_hours=req.jwt_ttl_hours,must_change_pwd=1)
    if p["role"]=="superadmin" and gid and req.notify_admin:
        g=D.get_group(gid)
        if g:
            adm=D.get_user_by_id(g["admin_id"])
            if adm:D.push_notif(adm["id"],"user_assigned",f"Nouvel utilisateur : {req.login}",body=f"Placé dans {g['name']} par superadmin",ref_id=u["id"])
    D.log_event("user_created",user_id=u["id"],user_login=u["login"],role="user",admin_id=admin_id,group_id=gid)
    return{k:v for k,v in u.items() if k!="pwd_hash"}

@app.patch("/api/users/{uid}")
async def update_user(uid:str,req:UpdateUserReq,p=Depends(require_auth)):
    role=p["role"];u=D.get_user_by_id(uid)
    if not u or u["role"]!="user":raise HTTPException(404)
    if role=="admin" and u["admin_id"]!=p["sub"]:raise HTTPException(403)
    ups={}
    if req.badge_quota is not None:ups["badge_quota"]=req.badge_quota
    if req.jwt_ttl_hours is not None:ups["jwt_ttl_hours"]=req.jwt_ttl_hours
    if req.is_active is not None:ups["is_active"]=req.is_active
    if req.group_id is not None:
        if role=="admin":
            g=D.get_group(req.group_id)
            if not g or g["admin_id"]!=p["sub"]:raise HTTPException(403)
        ups["group_id"]=req.group_id
    if req.admin_id is not None and role=="superadmin":ups["admin_id"]=req.admin_id
    D.update_user(uid,**ups)
    if req.is_active==0:D.log_event("user_blocked",user_id=uid,user_login=u["login"],admin_id=p["sub"])
    return{"ok":True}

@app.delete("/api/users/{uid}",status_code=204)
async def delete_user(uid:str,p=Depends(require_auth)):
    role=p["role"];u=D.get_user_by_id(uid)
    if not u:raise HTTPException(404)
    if role=="admin":
        if u["admin_id"]!=p["sub"]:raise HTTPException(403)
        D.soft_delete_user(uid,p["sub"])
        sa=D.get_superadmin()
        if sa:D.push_notif(sa["id"],"delete_user",f"Suppression en attente : {u['login']}",body=f"Par {p['login']}",ref_id=uid)
        D.log_event("user_deleted_soft",user_id=uid,user_login=u["login"],admin_id=p["sub"])
    else:
        D.wipe_user_badges(uid)
        with D.db() as conn:conn.execute("DELETE FROM users WHERE id=?",(uid,))
        D.log_event("user_deleted_final",user_id=uid,user_login=u["login"])
    return Response(status_code=204)

@app.post("/api/users/{uid}/restore")
async def restore_user(uid:str,p=Depends(require_role("superadmin"))):
    D.restore_user(uid);u=D.get_user_by_id(uid)
    D.log_event("user_restored",user_id=uid,user_login=u["login"] if u else "")
    return{"ok":True}

@app.post("/api/users/{uid}/reset-password")
async def reset_user_pwd(uid:str,body:dict,p=Depends(require_auth)):
    role=p["role"];u=D.get_user_by_id(uid)
    if not u:raise HTTPException(404)
    if role=="admin" and u["admin_id"]!=p["sub"]:raise HTTPException(403)
    err=D.validate_pwd(body.get("password",""))
    if err:raise HTTPException(400,err)
    D.update_user(uid,pwd_hash=D.hash_pwd(body["password"]),must_change_pwd=1)
    if body.get("wipe_badges"):D.wipe_user_badges(uid)
    D.log_event("password_reset",user_id=uid,user_login=u["login"],admin_id=p["sub"])
    return{"ok":True}

@app.post("/api/users/{uid}/move-group")
async def move_group(uid:str,req:MoveUserGroupReq,p=Depends(require_auth)):
    role=p["role"];u=D.get_user_by_id(uid)
    if not u:raise HTTPException(404)
    if role=="admin":
        if u["admin_id"]!=p["sub"]:raise HTTPException(403)
        g=D.get_group(req.group_id)
        if not g or g["admin_id"]!=p["sub"]:raise HTTPException(403)
    old=u["group_id"];D.update_user(uid,group_id=req.group_id)
    if req.notify and role=="admin":
        sa=D.get_superadmin()
        if sa:D.push_notif(sa["id"],"group_change",f"Changement groupe : {u['login']}",body=f"Par {p['login']}",ref_id=uid)
    D.log_event("user_group_changed",user_id=uid,user_login=u["login"],group_id=req.group_id,admin_id=p["sub"],detail={"from":old,"to":req.group_id})
    return{"ok":True}

@app.get("/api/groups")
async def list_groups(p=Depends(require_auth)):
    role=p["role"]
    gs=D.get_all_groups() if role=="superadmin" else D.get_groups_by_admin(p["sub"])
    result=[]
    for g in gs:
        ug=[u for u in D.get_users_by_admin(g["admin_id"]) if u["group_id"]==g["id"]]
        adm=D.get_user_by_id(g["admin_id"])
        result.append({**g,"user_count":len(ug),"admin_login":adm["login"] if adm else "?"})
    return result

@app.post("/api/groups",status_code=201)
async def create_group(req:CreateGroupReq,p=Depends(require_auth)):
    role=p["role"]
    if role=="user":raise HTTPException(403)
    if role=="superadmin":
        admin_id=req.admin_id if req.admin_id else p["sub"]
        if req.admin_id:
            ta=D.get_user_by_id(req.admin_id)
            if not ta or ta["role"]!="admin":raise HTTPException(400,"Admin introuvable")
    else:
        admin_id=p["sub"]
        lim=int(D.get_config(f"admin_group_limit_{p['sub']}","0"))
        if lim>0 and D.count_admin_groups(p["sub"])>=lim:raise HTTPException(400,f"Limite de groupes atteinte ({lim})")
    g=D.create_group(name=req.name,admin_id=admin_id,color=req.color)
    D.log_event("group_created",user_id=p["sub"],user_login=p["login"],group_id=g["id"])
    return g

@app.patch("/api/groups/{gid}")
async def update_group(gid:str,req:CreateGroupReq,p=Depends(require_auth)):
    g=D.get_group(gid)
    if not g:raise HTTPException(404)
    if p["role"]=="admin" and g["admin_id"]!=p["sub"]:raise HTTPException(403)
    return D.update_group(gid,name=req.name,color=req.color)

@app.delete("/api/groups/{gid}",status_code=204)
async def delete_group(gid:str,p=Depends(require_auth)):
    g=D.get_group(gid)
    if not g:raise HTTPException(404)
    if p["role"]=="admin" and g["admin_id"]!=p["sub"]:raise HTTPException(403)
    D.delete_group(gid)
    if p["role"]=="admin":
        sa=D.get_superadmin()
        if sa:D.push_notif(sa["id"],"group_deleted",f"Groupe supprimé : {g['name']}",body="Utilisateurs suspendus.")
    D.log_event("group_deleted",user_id=p["sub"],user_login=p["login"],group_id=gid)
    return Response(status_code=204)

@app.get("/api/badges")
async def list_badges(p=Depends(require_auth)):
    if p["role"]=="superadmin":
        r=[]
        for u in D.get_all_users():
            for b in D.get_badges_by_owner(u["id"]):r.append({**b,"owner_login":u["login"]})
        return r
    # Badges normaux du user + badges stock qui lui ont été attribués
    badges = D.get_badges_by_owner(p["sub"])
    stock_attributed = [b for b in D.get_stock_badges()
                        if b["attributed_to"] == p["sub"]]
    return badges + stock_attributed

@app.post("/api/badges",status_code=201)
async def create_badge(req:CreateBadgeReq,p=Depends(require_auth)):
    uid=p["sub"];u=D.get_user_by_id(uid)
    if D.count_user_badges(uid)>=u["badge_quota"]:raise HTTPException(400,f"Quota atteint ({u['badge_quota']})")
    if D.uid_exists_for_user(uid,req.uid):raise HTTPException(409,f"UID {req.uid} déjà enregistré")
    b=D.create_badge(name=req.name,uid=req.uid,icon=req.icon,owner_id=uid)
    D.log_event("badge_created",user_id=uid,user_login=p["login"],detail={"name":req.name,"uid":req.uid})
    return b

@app.patch("/api/badges/{bid}")
async def update_badge(bid:str,req:UpdateBadgeReq,p=Depends(require_auth)):
    b=D.get_badge(bid)
    if not b:raise HTTPException(404)
    if p["role"]!="superadmin" and b["owner_id"]!=p["sub"]:raise HTTPException(403)
    if b.get("is_stock") and b.get("stock_status")=="attributed" and (req.name is not None or req.uid is not None):
        raise HTTPException(403,"Badge attribué — nom et UID non modifiables")
    ups={}
    if req.name is not None:ups["name"]=req.name
    if req.icon is not None:ups["icon"]=req.icon
    if req.uid is not None:
        if D.uid_exists_for_user(b["owner_id"],req.uid,exclude_badge_id=bid):raise HTTPException(409,f"UID {req.uid} déjà utilisé")
        ups["uid"]=req.uid
    return D.update_badge(bid,**ups)

@app.delete("/api/badges/{bid}",status_code=204)
async def delete_badge(bid:str,p=Depends(require_auth)):
    b=D.get_badge(bid)
    if not b:raise HTTPException(404)
    if p["role"]!="superadmin" and b["owner_id"]!=p["sub"]:raise HTTPException(403)
    D.delete_badge(bid);return Response(status_code=204)

@app.get("/api/stock")
async def list_stock(p=Depends(require_auth)):
    # Superadmin voit tout, admin voit uniquement ce qui lui est attribué
    if p["role"]=="superadmin":
        return D.get_stock_badges()
    elif p["role"]=="admin":
        all_stock=D.get_stock_badges()
        return[b for b in all_stock if b["attributed_to"]==p["sub"]]
    raise HTTPException(403)

@app.post("/api/stock",status_code=201)
async def add_stock(req:StockBadgeReq,p=Depends(require_role("superadmin"))):
    b=D.create_badge(name=req.name,uid=req.uid,icon=req.icon,owner_id=p["sub"],is_stock=True)
    D.log_event("stock_badge_created",user_id=p["sub"],user_login=p["login"],detail={"name":req.name,"uid":req.uid})
    return b

@app.post("/api/stock/{bid}/attribute")
async def attribute_stock(bid:str,req:AttributeStockReq,p=Depends(require_auth)):
    if p["role"] not in ("superadmin","admin"):raise HTTPException(403)
    b=D.get_badge(bid)
    if not b or not b["is_stock"]:raise HTTPException(404)
    if b["stock_status"]=="attributed" and p["role"]=="superadmin":
        raise HTTPException(400,"Déjà attribué")
    # Admin ne peut dispatcher que les badges qui lui ont été attribués
    if p["role"]=="admin" and b["attributed_to"]!=p["sub"]:
        raise HTTPException(403,"Ce badge ne vous a pas été attribué")
    t=D.get_user_by_id(req.attributed_to)
    if not t:raise HTTPException(404,"Destinataire introuvable")
    # Admin ne peut dispatcher qu'à ses propres users
    if p["role"]=="admin" and t["admin_id"]!=p["sub"]:
        raise HTTPException(403,"Cet utilisateur n'est pas dans votre périmètre")
    D.update_badge(bid,stock_status="attributed",attributed_to=req.attributed_to)
    msg="Vous pouvez le dispatcher à vos utilisateurs." if t["role"]=="admin" else "Ce badge est disponible dans vos accès."
    D.push_notif(t["id"],"badge_attributed",f"Badge attribué : {b['name']}",body=f"UID : {b['uid']} — {msg}",ref_id=bid)
    D.log_event("stock_badge_attributed",user_id=p["sub"],user_login=p["login"],detail={"badge":b["name"],"to":t["login"]})
    return{"ok":True}

@app.post("/api/stock/{bid}/reclaim")
async def reclaim_stock(bid:str,p=Depends(require_role("superadmin"))):
    b=D.get_badge(bid)
    if not b or not b["is_stock"]:raise HTTPException(404)
    D.update_badge(bid,stock_status="available",attributed_to=None);return{"ok":True}

@app.delete("/api/stock/{bid}",status_code=204)
async def delete_stock(bid:str,p=Depends(require_role("superadmin"))):
    b=D.get_badge(bid)
    if not b or not b["is_stock"]:raise HTTPException(404)
    D.delete_badge(bid);return Response(status_code=204)

@app.post("/api/badges/{bid}/encode")
async def encode_badge(bid:str,p=Depends(require_auth)):
    global _queue_count
    b=D.get_badge(bid)
    if not b:raise HTTPException(404)
    # Autoriser si : superadmin, admin, owner, ou badge stock attribué à ce user
    is_owner = b["owner_id"] == p["sub"]
    is_attributed = b.get("is_stock") and b.get("attributed_to") == p["sub"]
    if p["role"] not in("superadmin","admin") and not is_owner and not is_attributed:
        raise HTTPException(403)
    uid=p["sub"];lim=int(D.get_config("mct_daily_limit","5"));used=D.count_mct_last_24h(uid)
    if used>=lim and p["role"] not in("superadmin","admin"):raise HTTPException(429,f"Limite MCT atteinte ({lim}/24h)")
    if _queue_count>=MAX_QUEUE:raise HTTPException(503,"Serveur occupé")
    _queue_count+=1
    try:
        async with _wine_sem:
            mp=await asyncio.get_event_loop().run_in_executor(None,_encode_sync,b["uid"],b["name"],b["owner_id"],p["login"])
    finally:_queue_count-=1
    sz=mp.stat().st_size if mp.exists() else 0
    dur=int(D.get_config("vigik_duration_hours","84"))
    D.record_mct(bid,uid,str(mp),sz,dur);D.update_badge(bid,last_encoded=D.now())
    D.log_event("mct_generated",user_id=uid,user_login=p["login"],detail={"badge":b["name"],"uid":b["uid"],"size":sz})
    return FileResponse(path=str(mp),media_type="application/octet-stream",filename=mp.name,headers={"X-Badge-Name":b["name"],"X-Badge-UID":b["uid"]})

def _encode_sync(uid,name,owner_id,login):
    uid=uid.upper();dur=int(D.get_config("vigik_duration_hours","84"))
    od=Path(CONFIG["mct_output_dir"])/owner_id;od.mkdir(parents=True,exist_ok=True)
    ts=datetime.now().strftime("%Y%m%d_%H%M%S");jp=od/f"tmp_{uid}_{ts}.json"
    sn=name.replace(" ","_").replace("/","-")[:30];mp=od/f"badge_{sn}_{uid}_{ts}.mct"
    if not Path(CONFIG["cert_file"]).exists():raise HTTPException(500,"cert.txt introuvable")
    if not Path(CONFIG["vigik_exe"]).exists():raise HTTPException(500,"vigik_loader_cli.exe introuvable")
    cmd=["wine",CONFIG["vigik_exe"],"-c",CONFIG["cert_file"],"-u",uid,"-o","json","-f",str(jp),"-d",str(dur)]
    try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=30,env={**os.environ,"WINEDEBUG":"-all"})
    except subprocess.TimeoutExpired:raise HTTPException(500,"Timeout Wine")
    except FileNotFoundError:raise HTTPException(500,"Wine non installé")
    if not jp.exists():raise HTTPException(500,f"Erreur vigik: {r.stderr[:200]}")
    try:mfd=_j2mfd(jp)
    except Exception as e:jp.unlink(missing_ok=True);raise HTTPException(500,f"JSON→MFD: {e}")
    jp.unlink(missing_ok=True);mp.write_text(_mfd2mct(mfd,uid,name),encoding="utf-8");return mp

def _j2mfd(jp):
    d=json.loads(jp.read_text());blk={b["id"]:bytes.fromhex(b["value"]) for b in d["blocks"]}
    mfd=bytearray(1024)
    for bid,v in blk.items():mfd[bid*16:(bid+1)*16]=v
    mfd[4]=mfd[0]^mfd[1]^mfd[2]^mfd[3];return bytes(mfd)

def _mfd2mct(mfd,uid="",name=""):
    lines=[f"# Badge Manager: {name}",f"# UID: {uid.upper()}",f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",""]
    off=0
    for s in range(5):
        lines.append(f"+Sector: {s}")
        for _ in range(4):lines.append(mfd[off:off+16].hex().upper());off+=16
    return"\n".join(lines)+"\n"

@app.get("/api/mct-history")
async def mct_history(p=Depends(require_auth)):return D.get_mct_history_by_user(p["sub"])

@app.get("/api/mct-quota")
async def mct_quota(p=Depends(require_auth)):
    lim=int(D.get_config("mct_daily_limit","5"));used=D.count_mct_last_24h(p["sub"])
    return{"used":used,"limit":lim,"remaining":max(0,lim-used)}

@app.get("/api/requests")
async def list_requests(p=Depends(require_auth)):
    role=p["role"]
    if role=="superadmin":reqs=D.get_pending_requests()
    elif role=="admin":reqs=D.get_pending_requests(for_admin_id=p["sub"])
    else:
        with D.db() as conn:rows=conn.execute("SELECT * FROM requests WHERE requester_id=? ORDER BY created_at DESC",(p["sub"],)).fetchall()
        return[dict(r) for r in rows]
    return[{**r,"requester_login":(D.get_user_by_id(r["requester_id"]) or {}).get("login","?")} for r in reqs]

@app.post("/api/requests",status_code=201)
async def create_request(req:RequestReq,p=Depends(require_auth)):
    if D.has_pending_request(p["sub"],req.type):raise HTTPException(400,"Demande en attente du même type")
    r=D.create_request(type_=req.type,requester_id=p["sub"],motif=req.motif,target_id=req.target_id,group_to=req.group_to)
    u=D.get_user_by_id(p["sub"]);adm=D.get_user_by_id(u["admin_id"]) if u and u["admin_id"] else None;sa=D.get_superadmin()
    title=f"Nouvelle demande : {req.type.replace('_',' ')}";body=f"De {p['login']} : {req.motif or ''}"[:100]
    if adm:D.push_notif(adm["id"],"new_request",title,body=body,ref_id=r["id"])
    if sa:D.push_notif(sa["id"],"new_request",title,body=body,ref_id=r["id"])
    D.log_event("demande_submitted",user_id=p["sub"],user_login=p["login"],detail={"type":req.type})
    return r

@app.patch("/api/requests/{rid}")
async def handle_request(rid:str,body:dict,p=Depends(require_auth)):
    status=body.get("status")
    if status not in("approved","refused"):raise HTTPException(400)
    req=D.get_request(rid)
    if not req:raise HTTPException(404)
    if req["status"]!="pending":raise HTTPException(400,"Déjà traitée")
    if p["role"]=="admin":
        rq=D.get_user_by_id(req["requester_id"])
        if not rq or rq["admin_id"]!=p["sub"]:raise HTTPException(403)
    D.update_request(rid,status,p["sub"])
    rq=D.get_user_by_id(req["requester_id"])
    if rq:D.push_notif(rq["id"],"request_handled",f"Demande {'approuvée' if status=='approved' else 'refusée'} : {req['type'].replace('_',' ')}",ref_id=rid)
    return{"ok":True}

@app.get("/api/messages/contacts")
async def get_contacts(p=Depends(require_auth)):
    role=p["role"];contacts=[]
    if role=="user":
        u=D.get_user_by_id(p["sub"])
        if u and u["admin_id"]:
            a=D.get_user_by_id(u["admin_id"])
            if a:contacts.append({"id":a["id"],"login":a["login"],"role":"admin"})
    elif role=="admin":
        contacts=[{"id":u["id"],"login":u["login"],"role":"user"} for u in D.get_users_by_admin(p["sub"])]
    elif role=="superadmin":
        contacts=[{"id":a["id"],"login":a["login"],"role":"admin"} for a in D.get_all_admins()]
        contacts+=[{"id":u["id"],"login":u["login"],"role":"user"} for u in D.get_all_users()]
    return contacts

@app.get("/api/messages/conversations")
async def conversations(p=Depends(require_auth)):return D.get_conversations_list(p["sub"])

@app.get("/api/messages/{oid}")
async def get_conv(oid:str,p=Depends(require_auth)):
    o=D.get_user_by_id(oid)
    if not o:raise HTTPException(404)
    D.mark_messages_read(p["sub"],oid);return D.get_conversation(p["sub"],oid)

@app.post("/api/messages")
async def send_msg(req:SendMsgReq,p=Depends(require_auth)):
    o=D.get_user_by_id(req.to_id)
    if not o:raise HTTPException(404,"Destinataire introuvable")
    msg=D.send_message(from_id=p["sub"],to_id=req.to_id,content=req.content)
    D.push_notif(req.to_id,"new_message",f"Message de {p['login']}",body=req.content[:50],ref_id=p["sub"])
    return msg

@app.get("/api/notifications")
async def get_notifs(p=Depends(require_auth)):
    return{"notifications":D.get_notifs(p["sub"]),"unread_notifs":D.count_unread_notifs(p["sub"]),"unread_messages":D.count_unread_messages(p["sub"])}

@app.post("/api/notifications/read")
async def mark_read(p=Depends(require_auth)):
    D.mark_notifs_read(p["sub"]);return{"ok":True}

@app.get("/api/dashboard")
async def dashboard(p=Depends(require_auth)):
    role=p["role"]
    if role=="superadmin":
        s=D.get_global_stats();return{**s,"heatmap":D.get_heatmap_data(),"mct_by_day":D.get_mct_by_day(7),"disk":D.get_disk_usage()}
    elif role=="admin":
        us=D.get_users_by_admin(p["sub"]);gs=D.get_groups_by_admin(p["sub"])
        return{"user_count":len(us),"group_count":len(gs),"badge_count":sum(D.count_user_badges(u["id"]) for u in us),"mct_today":sum(D.count_mct_last_24h(u["id"]) for u in us),"pending_requests":len(D.get_pending_requests(for_admin_id=p["sub"]))}
    else:
        bs=D.get_badges_by_owner(p["sub"]);u=D.get_user_by_id(p["sub"]);lim=int(D.get_config("mct_daily_limit","5"))
        return{"badge_count":len(bs),"badge_quota":u["badge_quota"],"mct_used":D.count_mct_last_24h(p["sub"]),"mct_limit":lim}

@app.get("/api/logs")
async def get_logs(limit:int=100,event:str=None,p=Depends(require_role("superadmin"))):
    return D.get_logs(limit=min(limit,1000),event_filter=event)

@app.get("/api/logs/export")
async def export_logs(p=Depends(require_role("superadmin")),format:str="json"):
    """Export du journal — format=json (défaut) ou format=csv."""
    logs = D.get_logs(limit=100000)
    from fastapi.responses import StreamingResponse
    if format == "csv":
        import csv, io
        output = io.StringIO()
        if logs:
            writer = csv.DictWriter(output, fieldnames=logs[0].keys())
            writer.writeheader()
            writer.writerows(logs)
        content = output.getvalue().encode("utf-8-sig")
        return StreamingResponse(iter([content]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=logs_{D.now()[:10]}.csv"})
    # JSON (défaut)
    for log in logs:
        try: log["detail"] = json.loads(log.get("detail") or "{}")
        except: log["detail"] = {}
    export = {
        "exported_at": D.now(), "exported_by": p["login"],
        "version": "2", "total": len(logs), "logs": logs,
    }
    content = json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8")
    return StreamingResponse(iter([content]), media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=logs_{D.now()[:10]}.json"})

# ─── Import / Export badges ───────────────────────────────────────────────────

@app.get("/api/badges/export")
async def export_badges(p=Depends(require_auth)):
    """Export des badges en JSON."""
    import json as _json
    role=p["role"]; uid=p["sub"]; login=p["login"]
    if role=="superadmin":
        badges=[]
        for u in D.get_all_users():
            for b in D.get_badges_by_owner(u["id"]):
                badges.append({**b,"owner_login":u["login"]})
        for b in D.get_stock_badges():
            badges.append({**b,"owner_login":"superadmin_stock"})
    else:
        badges=D.get_badges_by_owner(uid)
        badges+=[b for b in D.get_stock_badges() if b.get("attributed_to")==uid]
    export_data={
        "exported_by":login,"exported_at":D.now(),"role":role,
        "badges":[{"name":b["name"],"uid":b["uid"],"icon":b.get("icon","🔑")} for b in badges]
    }
    content=_json.dumps(export_data,ensure_ascii=False,indent=2).encode("utf-8")
    from fastapi.responses import StreamingResponse
    return StreamingResponse(iter([content]),media_type="application/json",
        headers={"Content-Disposition":f"attachment; filename=badges_{login}_{D.now()[:10]}.json"})

class BadgeImportReq(BaseModel):
    badges: list  # liste de {name, uid, icon}
    overwrite: bool = False  # si True, skip les doublons silencieusement

@app.post("/api/badges/import")
async def import_badges(req: BadgeImportReq, p=Depends(require_auth)):
    """Import de badges depuis un fichier JSON exporté."""
    user_id = p["sub"]
    user = D.get_user_by_id(user_id)
    imported = 0; skipped = 0; errors = []

    for item in req.badges:
        name = str(item.get("name","")).strip()[:50]
        uid  = str(item.get("uid","")).strip().upper()
        icon = str(item.get("icon","🔑"))
        if not name or len(uid) != 8:
            skipped += 1; continue
        # Validation UID
        ok, msg = validate_uid(uid)
        if not ok:
            errors.append(f"{uid}: {msg}"); skipped += 1; continue
        # Vérif quota
        current = D.count_user_badges(user_id)
        if current >= user["badge_quota"]:
            errors.append(f"Quota atteint ({user['badge_quota']}) — import interrompu")
            break
        # Vérif doublon
        if D.uid_exists_for_user(user_id, uid):
            if req.overwrite:
                skipped += 1; continue
            else:
                errors.append(f"{uid}: déjà existant"); skipped += 1; continue
        D.create_badge(name=name, uid=uid, icon=icon, owner_id=user_id)
        D.log_event("badge_imported", user_id=user_id, user_login=p["login"],
                    detail={"name": name, "uid": uid})
        imported += 1

    return {"imported": imported, "skipped": skipped, "errors": errors}

@app.post("/api/superadmin/dispatch")
async def superadmin_dispatch(req:DispatchReq,p=Depends(require_role("superadmin"))):
    sa_id=p["sub"];sa_login=p["login"]

    if req.type=="group_to_admin":
        if not req.group_id or not req.admin_id:raise HTTPException(400,"group_id et admin_id requis")
        g=D.get_group(req.group_id)
        if not g:raise HTTPException(404,"Groupe introuvable")
        new_adm=D.get_user_by_id(req.admin_id)
        if not new_adm or new_adm["role"]!="admin":raise HTTPException(404,"Admin introuvable")
        old_adm=D.get_user_by_id(g["admin_id"]) if g["admin_id"]!=req.admin_id else None
        ts=D.now()
        with D.db() as conn:
            users_in_group=[dict(r) for r in conn.execute(
                "SELECT * FROM users WHERE group_id=? AND is_deleted=0",(req.group_id,)).fetchall()]
            conn.execute("UPDATE groups SET admin_id=? WHERE id=?",(req.admin_id,req.group_id))
            conn.execute("UPDATE users SET admin_id=?,updated_at=? WHERE group_id=? AND is_deleted=0",
                (req.admin_id,ts,req.group_id))
        nb=len(users_in_group)
        D.push_notif(new_adm["id"],"dispatch",f"Groupe dispatché : {g['name']}",
            body=f"{nb} utilisateur(s) transféré(s) par le superadmin")
        D.send_message(sa_id,new_adm["id"],
            f"Le groupe « {g['name']} » ({nb} utilisateur(s)) vous a été assigné par le superadmin.")
        if old_adm:
            D.push_notif(old_adm["id"],"dispatch",f"Groupe retiré : {g['name']}",
                body=f"Transféré à {new_adm['login']} par {sa_login}")
            D.send_message(sa_id,old_adm["id"],
                f"Le groupe « {g['name']} » a été transféré à l'admin « {new_adm['login']} » par le superadmin.")
        for u in users_in_group:
            D.push_notif(u["id"],"dispatch","Votre groupe a un nouvel administrateur",
                body=f"Groupe {g['name']} — nouvel admin : {new_adm['login']}")
        D.log_event("dispatch_group_to_admin",user_id=sa_id,user_login=sa_login,
            group_id=req.group_id,admin_id=req.admin_id,
            detail={"group":g["name"],"new_admin":new_adm["login"],"users_moved":nb})
        return{"ok":True,"group":g["name"],"admin":new_adm["login"],"users_moved":nb}

    elif req.type=="user_to_group":
        if not req.user_id or not req.group_id:raise HTTPException(400,"user_id et group_id requis")
        u=D.get_user_by_id(req.user_id)
        if not u or u["role"]!="user" or u["is_deleted"]:raise HTTPException(404,"Utilisateur introuvable")
        g=D.get_group(req.group_id)
        if not g:raise HTTPException(404,"Groupe introuvable")
        new_adm=D.get_user_by_id(g["admin_id"])
        old_adm=D.get_user_by_id(u["admin_id"]) if u["admin_id"] and u["admin_id"]!=g["admin_id"] else None
        D.update_user(req.user_id,group_id=req.group_id,admin_id=g["admin_id"])
        adm_name=new_adm["login"] if new_adm else "?"
        if new_adm:
            D.push_notif(new_adm["id"],"dispatch",f"Nouvel utilisateur : {u['login']}",
                body=f"Placé dans {g['name']} par le superadmin")
            D.send_message(sa_id,new_adm["id"],
                f"L'utilisateur « {u['login']} » a été placé dans votre groupe « {g['name']} » par le superadmin.")
        if old_adm:
            D.push_notif(old_adm["id"],"dispatch",f"Utilisateur transféré : {u['login']}",
                body=f"Vers {g['name']} (admin {adm_name}) par {sa_login}")
            D.send_message(sa_id,old_adm["id"],
                f"L'utilisateur « {u['login']} » a été transféré au groupe « {g['name']} » par le superadmin.")
        D.push_notif(u["id"],"dispatch",f"Vous avez été placé dans le groupe {g['name']}",
            body=f"Admin : {adm_name}")
        D.log_event("dispatch_user_to_group",user_id=sa_id,user_login=sa_login,
            group_id=req.group_id,admin_id=g["admin_id"],detail={"user":u["login"],"group":g["name"]})
        return{"ok":True,"user":u["login"],"group":g["name"]}

    else:  # user_to_admin
        if not req.user_id or not req.admin_id:raise HTTPException(400,"user_id et admin_id requis")
        u=D.get_user_by_id(req.user_id)
        if not u or u["role"]!="user" or u["is_deleted"]:raise HTTPException(404,"Utilisateur introuvable")
        new_adm=D.get_user_by_id(req.admin_id)
        if not new_adm or new_adm["role"]!="admin":raise HTTPException(404,"Admin introuvable")
        old_adm=D.get_user_by_id(u["admin_id"]) if u["admin_id"] and u["admin_id"]!=req.admin_id else None
        updates={"admin_id":req.admin_id}
        old_grp=None
        if u["group_id"]:
            g=D.get_group(u["group_id"])
            if g and g["admin_id"]!=req.admin_id:updates["group_id"]=None;old_grp=g
        D.update_user(req.user_id,**updates)
        grp_note=f" (retiré du groupe « {old_grp['name']} »)" if old_grp else ""
        D.push_notif(new_adm["id"],"dispatch",f"Nouvel utilisateur : {u['login']}",
            body=f"Assigné par le superadmin{grp_note}")
        D.send_message(sa_id,new_adm["id"],
            f"L'utilisateur « {u['login']} » vous a été assigné par le superadmin." +
            (f" Il a été retiré du groupe « {old_grp['name']} »." if old_grp else ""))
        if old_adm:
            D.push_notif(old_adm["id"],"dispatch",f"Utilisateur transféré : {u['login']}",
                body=f"Vers admin {new_adm['login']} par {sa_login}")
            D.send_message(sa_id,old_adm["id"],
                f"L'utilisateur « {u['login']} » a été transféré à l'admin « {new_adm['login']} » par le superadmin.")
        D.push_notif(u["id"],"dispatch","Votre compte a été transféré",
            body=f"Nouvel admin : {new_adm['login']}")
        D.log_event("dispatch_user_to_admin",user_id=sa_id,user_login=sa_login,
            admin_id=req.admin_id,detail={"user":u["login"],"new_admin":new_adm["login"]})
        return{"ok":True,"user":u["login"],"admin":new_adm["login"]}

@app.get("/api/config")
async def get_cfg(p=Depends(require_role("superadmin"))):
    return{k:D.get_config(k) for k in["badge_quota_default","mct_daily_limit","jwt_ttl_hours_default","vigik_duration_hours","disk_alert_threshold_pct"]}

@app.patch("/api/config")
async def upd_cfg(req:ConfigUpdateReq,p=Depends(require_role("superadmin"))):
    m={"badge_quota_default":req.badge_quota_default,"mct_daily_limit":req.mct_daily_limit,"jwt_ttl_hours_default":req.jwt_ttl_hours_default,"vigik_duration_hours":req.vigik_duration_hours,"disk_alert_threshold_pct":req.disk_alert_threshold_pct}
    for k,v in m.items():
        if v is not None:D.set_config(k,str(v))
    return{"ok":True}

@app.get("/api/health")
async def health():
    wo=subprocess.run(["which","wine"],capture_output=True).returncode==0
    return{"status":"ok","wine":wo,"vigik_exe":Path(CONFIG["vigik_exe"]).exists(),"cert":Path(CONFIG["cert_file"]).exists(),"disk":D.get_disk_usage(),"queue":_queue_count}

app.mount("/static",StaticFiles(directory=str(BASE_DIR/"static_v2")),name="static_v2")

@app.get("/{fp:path}")
async def pwa(fp:str):return FileResponse(str(BASE_DIR/"static_v2"/"index.html"))

async def _cleanup_loop():
    while True:
        await asyncio.sleep(3600)
        n=D.cleanup_expired_mct()
        if n:D.log_event("mct_cleanup",detail={"deleted":n})

async def _watchdog_loop():
    await asyncio.sleep(30)
    while True:
        try:
            ram=psutil.virtual_memory().percent;cpu=psutil.cpu_percent(interval=1);disk=D.get_disk_usage()
            D.log_event("watchdog_ok",detail={"ram":ram,"cpu":cpu,"disk":disk["pct"],"queue":_queue_count})
            alerts=[]
            if ram>85:alerts.append(f"RAM {ram}%")
            if cpu>80:alerts.append(f"CPU {cpu}%")
            if disk["alert"]:alerts.append(f"Disque {disk['pct']}%")
            if alerts:
                sa=D.get_superadmin()
                if sa:D.push_notif(sa["id"],"system_alert","⚠️ Alerte système",body=" · ".join(alerts))
        except:pass
        await asyncio.sleep(60)

if __name__=="__main__":
    import uvicorn
    sc=CONFIG["ssl_cert"] if Path(CONFIG["ssl_cert"]).exists() else None
    sk=CONFIG["ssl_key"] if Path(CONFIG["ssl_key"]).exists() else None
    print(f"[*] Badge Manager v2.1 — port {CONFIG['port']}")
    uvicorn.run("server_v2:app",host=CONFIG["host"],port=CONFIG["port"],reload=False,ssl_certfile=sc,ssl_keyfile=sk)
