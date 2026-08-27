import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("WiseWater Production REST API & CMP Server running on port 8000 (v1.0.2)")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
