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


def siguiente_numero_cotizacion():
    last = db.cotizaciones.find_one({"numero": {"$regex": "^COT-"}}, sort=[("numero", -1)])
    if not last or not last.get("numero"):
        return "COT-000001"
    try:
        actual = int(str(last["numero"]).replace("COT-", ""))
    except Exception:
        actual = db.cotizaciones.count_documents({})
    return f"COT-{actual + 1:06d}"


@app.post("/cotizaciones")
def crear_cotizacion(data: dict):
    fecha = data.get("fecha", datetime.utcnow().date().isoformat())
    if not data.get("numero"):
        data["numero"] = siguiente_numero_cotizacion()
    data["fecha"] = fecha
    data["fecha_creacion"] = datetime.utcnow().isoformat()
    data["vigencia_dias"] = int(data.get("vigencia_dias", 15))
    try:
        from datetime import timedelta
        fecha_dt = datetime.fromisoformat(str(fecha)[:10])
        data["vigencia_hasta"] = (fecha_dt + timedelta(days=data["vigencia_dias"])).date().isoformat()
    except Exception:
        data["vigencia_hasta"] = data.get("vigencia_hasta", "")
    data["estado"] = data.get("estado", "Pendiente")
    data["iva_incluido"] = bool(data.get("iva_incluido", True))
    data["cantidad"] = float(data.get("cantidad", 0) or 0)
    data["precio"] = float(data.get("precio", 0) or 0)
    data["total"] = float(data.get("total", data["cantidad"] * data["precio"]) or 0)
    data["leyenda_iva"] = "Precio incluye IVA" if data["iva_incluido"] else "Precio no incluye IVA"
    data["origen"] = data.get("origen", "portal")
    result = db.cotizaciones.insert_one(data)
    return {"success": True, "id": str(result.inserted_id), "numero": data["numero"]}


@app.get("/cotizaciones")
def listar_cotizaciones():
    return [clean_doc(x) for x in db.cotizaciones.find().sort("fecha_creacion", -1)]


@app.put("/cotizaciones/{item_id}")
def actualizar_cotizacion(item_id: str, data: dict):
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    if "cantidad" in data:
        data["cantidad"] = float(data.get("cantidad") or 0)
    if "precio" in data:
        data["precio"] = float(data.get("precio") or 0)
    if "total" not in data and ("cantidad" in data or "precio" in data):
        actual = db.cotizaciones.find_one({"_id": oid}) or {}
        cantidad = float(data.get("cantidad", actual.get("cantidad", 0)) or 0)
        precio = float(data.get("precio", actual.get("precio", 0)) or 0)
        data["total"] = cantidad * precio
    if "iva_incluido" in data:
        data["iva_incluido"] = bool(data.get("iva_incluido"))
        data["leyenda_iva"] = "Precio incluye IVA" if data["iva_incluido"] else "Precio no incluye IVA"
    db.cotizaciones.update_one({"_id": oid}, {"$set": data})
    return {"success": True}


@app.delete("/cotizaciones/{item_id}")
def eliminar_cotizacion(item_id: str):
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    db.cotizaciones.delete_one({"_id": oid})
    return {"success": True}


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
