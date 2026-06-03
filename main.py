from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
import os
import certifi

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


def clean_doc(doc):
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc


def get_collection(name: str):
    allowed = ["clientes", "pedidos", "pagos", "cotizaciones", "contactos_web", "productos"]
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
