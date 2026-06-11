from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from datetime import datetime, timedelta
from bson import ObjectId
import os
import certifi
from passlib.context import CryptContext
from jose import jwt, JWTError

app = FastAPI(title="DUO-LINER API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "duoliner_db")

if not MONGO_URI:
    raise Exception("Falta la variable MONGODB_URI")

client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=10000
)

db = client[DB_NAME]

# =========================
# SEGURIDAD / USUARIOS
# =========================

SECRET_KEY = os.getenv("SECRET_KEY", "duo-liner-cambiar-esta-clave-en-render")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str):
    return pwd_context.verify(password, password_hash)


def create_access_token(data: dict):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autorizado")

    token = authorization.replace("Bearer ", "").strip()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = db.usuarios.find_one({"_id": oid, "activo": True})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario inválido")

    return user


def require_admin(user=Depends(get_current_user)):
    if user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")
    return user


def ensure_initial_admin():
    if db.usuarios.count_documents({}) == 0:
        db.usuarios.insert_one({
            "usuario": "admin",
            "nombre": "Administrador",
            "password_hash": hash_password("CambiaEstaClave123"),
            "rol": "admin",
            "activo": True,
            "fecha": datetime.utcnow().isoformat(),
            "debe_cambiar_password": True
        })


ensure_initial_admin()


@app.post("/auth/login")
def auth_login(data: dict):
    usuario = str(data.get("usuario", "")).strip().lower()
    password = str(data.get("password", ""))

    user = db.usuarios.find_one({"usuario": usuario, "activo": True})
    if not user or not verify_password(password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    token = create_access_token({
        "sub": str(user["_id"]),
        "usuario": user["usuario"],
        "rol": user.get("rol", "usuario")
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": user["usuario"],
        "nombre": user.get("nombre", ""),
        "rol": user.get("rol", "usuario"),
        "debe_cambiar_password": user.get("debe_cambiar_password", False)
    }


@app.get("/auth/me")
def auth_me(user=Depends(get_current_user)):
    return {
        "id": str(user["_id"]),
        "usuario": user.get("usuario", ""),
        "nombre": user.get("nombre", ""),
        "rol": user.get("rol", "usuario"),
        "activo": user.get("activo", True)
    }


@app.get("/usuarios")
def listar_usuarios(user=Depends(require_admin)):
    return [
        {
            "id": str(x["_id"]),
            "usuario": x.get("usuario", ""),
            "nombre": x.get("nombre", ""),
            "rol": x.get("rol", "usuario"),
            "activo": x.get("activo", True),
            "fecha": x.get("fecha", "")
        }
        for x in db.usuarios.find().sort("usuario", 1)
    ]


@app.post("/usuarios")
def crear_usuario(data: dict, user=Depends(require_admin)):
    usuario = str(data.get("usuario", "")).strip().lower()
    password = str(data.get("password", "")).strip()
    nombre = str(data.get("nombre", usuario)).strip()
    rol = str(data.get("rol", "usuario")).strip()

    if rol not in ["admin", "usuario"]:
        raise HTTPException(status_code=400, detail="Rol inválido")

    if not usuario or not password:
        raise HTTPException(status_code=400, detail="Usuario y contraseña son requeridos")

    if len(password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 8 caracteres")

    if db.usuarios.find_one({"usuario": usuario}):
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    result = db.usuarios.insert_one({
        "usuario": usuario,
        "nombre": nombre,
        "password_hash": hash_password(password),
        "rol": rol,
        "activo": bool(data.get("activo", True)),
        "fecha": datetime.utcnow().isoformat(),
        "debe_cambiar_password": False
    })

    return {"success": True, "id": str(result.inserted_id)}


@app.put("/usuarios/{item_id}")
def actualizar_usuario(item_id: str, data: dict, user=Depends(require_admin)):
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    target = db.usuarios.find_one({"_id": oid})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    update = {}

    if "nombre" in data:
        update["nombre"] = str(data.get("nombre", "")).strip()

    if "rol" in data:
        rol = str(data.get("rol", "usuario")).strip()
        if rol not in ["admin", "usuario"]:
            raise HTTPException(status_code=400, detail="Rol inválido")
        update["rol"] = rol

    if "activo" in data:
        update["activo"] = bool(data.get("activo"))

    if data.get("password"):
        password = str(data.get("password")).strip()
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 8 caracteres")
        update["password_hash"] = hash_password(password)
        update["debe_cambiar_password"] = False

    if update:
        db.usuarios.update_one({"_id": oid}, {"$set": update})

    return {"success": True}


@app.delete("/usuarios/{item_id}")
def eliminar_usuario(item_id: str, user=Depends(require_admin)):
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    if str(user["_id"]) == item_id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario")

    db.usuarios.update_one({"_id": oid}, {"$set": {"activo": False}})
    return {"success": True}


@app.put("/usuarios/{item_id}/activar")
def activar_usuario(item_id: str, user=Depends(require_admin)):
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    db.usuarios.update_one({"_id": oid}, {"$set": {"activo": True}})
    return {"success": True}


@app.put("/auth/cambiar-password")
def cambiar_mi_password(data: dict, user=Depends(get_current_user)):
    actual = str(data.get("actual", ""))
    nueva = str(data.get("nueva", ""))

    if not verify_password(actual, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    if len(nueva) < 8:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener mínimo 8 caracteres")

    db.usuarios.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "password_hash": hash_password(nueva),
            "debe_cambiar_password": False
        }}
    )

    return {"success": True}



def clean_doc(doc):
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc


def get_collection(name: str):
    allowed = ["clientes", "pedidos", "pagos", "cotizaciones", "contactos_web", "productos", "usuarios"]
    if name not in allowed:
        raise HTTPException(status_code=400, detail="Colección no permitida")
    return db[name]


@app.get("/")
def home():
    return {
        "empresa": "DUO-LINER",
        "status": "online",
        "database": DB_NAME
    }


@app.get("/health")
def health():
    try:
        client.admin.command("ping")
        return {"estado": "ok", "mongodb": "conectado"}
    except Exception as e:
        return {"estado": "error", "mongodb": str(e)}


# =========================
# CONTACTOS WEB / COTIZACIONES
# =========================

@app.post("/contactos")
def crear_contacto(data: dict):
    data["fecha"] = datetime.utcnow().isoformat()
    data["estado"] = data.get("estado", "Nuevo")
    result = db.contactos_web.insert_one(data)
    return {"success": True, "id": str(result.inserted_id)}


@app.get("/contactos")
def listar_contactos():
    return [clean_doc(x) for x in db.contactos_web.find().sort("fecha", -1)]


@app.post("/cotizaciones")
def crear_cotizacion(data: dict):
    data["fecha"] = datetime.utcnow().isoformat()
    data["estado"] = data.get("estado", "Pendiente")
    result = db.cotizaciones.insert_one(data)
    return {"success": True, "id": str(result.inserted_id)}


@app.get("/cotizaciones")
def listar_cotizaciones():
    return [clean_doc(x) for x in db.cotizaciones.find().sort("fecha", -1)]


def cotizacion_filter_by_id(item_id: str):
    filtros = [{"id": item_id}]

    try:
        filtros.insert(0, {"_id": ObjectId(item_id)})
    except Exception:
        pass

    return {"$or": filtros}


@app.put("/cotizaciones/{item_id}")
def actualizar_cotizacion(item_id: str, data: dict):
    filtro = cotizacion_filter_by_id(item_id)

    data["fecha_modificacion"] = datetime.utcnow().isoformat()

    result = db.cotizaciones.update_one(filtro, {"$set": data})

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Cotización no encontrada para actualizar: {item_id}"
        )

    return {"success": True, "id": item_id}


@app.delete("/cotizaciones/{item_id}")
def eliminar_cotizacion(item_id: str):
    filtro = cotizacion_filter_by_id(item_id)

    result = db.cotizaciones.delete_one(filtro)

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Cotización no encontrada para eliminar: {item_id}"
        )

    return {"success": True, "id": item_id}


# =========================
# CLIENTES
# =========================

@app.post("/clientes")
def crear_cliente(data: dict):
    data["fecha"] = data.get("fecha", datetime.utcnow().isoformat())
    result = db.clientes.insert_one(data)
    return {"success": True, "id": str(result.inserted_id)}


@app.get("/clientes")
def listar_clientes():
    return [clean_doc(x) for x in db.clientes.find().sort("fecha", -1)]


@app.delete("/clientes/{item_id}")
def eliminar_cliente(item_id: str):
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    cliente = db.clientes.find_one({"_id": oid})
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    db.clientes.delete_one({"_id": oid})
    db.pedidos.delete_many({"cliente_id": item_id})
    db.pagos.delete_many({"cliente_id": item_id})

    return {"success": True}


# =========================
# PEDIDOS
# =========================

@app.post("/pedidos")
def crear_pedido(data: dict):
    data["fecha"] = data.get("fecha", datetime.utcnow().isoformat())
    data["estado"] = data.get("estado", "Nuevo")
    result = db.pedidos.insert_one(data)
    return {"success": True, "id": str(result.inserted_id)}


@app.get("/pedidos")
def listar_pedidos():
    return [clean_doc(x) for x in db.pedidos.find().sort("fecha", -1)]


@app.put("/pedidos/{item_id}")
def actualizar_pedido(item_id: str, data: dict):
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    db.pedidos.update_one({"_id": oid}, {"$set": data})
    return {"success": True}


@app.delete("/pedidos/{item_id}")
def eliminar_pedido(item_id: str):
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    db.pedidos.delete_one({"_id": oid})
    db.pagos.delete_many({"pedido_id": item_id})
    return {"success": True}


# =========================
# PAGOS
# =========================

@app.post("/pagos")
def crear_pago(data: dict):
    data["fecha"] = data.get("fecha", datetime.utcnow().isoformat())
    result = db.pagos.insert_one(data)
    return {"success": True, "id": str(result.inserted_id)}


@app.get("/pagos")
def listar_pagos():
    return [clean_doc(x) for x in db.pagos.find().sort("fecha", -1)]


@app.delete("/pagos/{item_id}")
def eliminar_pago(item_id: str):
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")

    db.pagos.delete_one({"_id": oid})
    return {"success": True}


# =========================
# PRODUCTOS
# =========================

@app.post("/productos")
def crear_producto(data: dict):
    data["fecha"] = data.get("fecha", datetime.utcnow().isoformat())
    result = db.productos.insert_one(data)
    return {"success": True, "id": str(result.inserted_id)}


@app.get("/productos")
def listar_productos():
    return [clean_doc(x) for x in db.productos.find().sort("fecha", -1)]
