from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from datetime import datetime
import os
from bson import ObjectId

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

client = MongoClient(MONGO_URI)
db = client[DB_NAME]


def clean_doc(doc):
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc


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
        return {"status": "ok", "mongodb": "connected"}
    except Exception as e:
        return {"status": "error", "mongodb": str(e)}


@app.post("/contactos")
def crear_contacto(data: dict):
    data["fecha"] = datetime.utcnow().isoformat()
    data["estado"] = "Nuevo"
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


@app.post("/clientes")
def crear_cliente(data: dict):
    data["fecha"] = datetime.utcnow().isoformat()
    result = db.clientes.insert_one(data)
    return {"success": True, "id": str(result.inserted_id)}


@app.get("/clientes")
def listar_clientes():
    return [clean_doc(x) for x in db.clientes.find().sort("fecha", -1)]


@app.post("/pedidos")
def crear_pedido(data: dict):
    data["fecha"] = datetime.utcnow().isoformat()
    data["estado"] = data.get("estado", "Nuevo")
    result = db.pedidos.insert_one(data)
    return {"success": True, "id": str(result.inserted_id)}


@app.get("/pedidos")
def listar_pedidos():
    return [clean_doc(x) for x in db.pedidos.find().sort("fecha", -1)]


@app.post("/productos")
def crear_producto(data: dict):
    data["fecha"] = datetime.utcnow().isoformat()
    result = db.productos.insert_one(data)
    return {"success": True, "id": str(result.inserted_id)}


@app.get("/productos")
def listar_productos():
    return [clean_doc(x) for x in db.productos.find().sort("fecha", -1)]
