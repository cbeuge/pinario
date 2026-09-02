from app import create_app

app = create_app()

if __name__ == "__main__":
    # Nur für die Entwicklung. Auf dem Server startet gunicorn `app` direkt
    # und dieser Block läuft gar nicht. Port 5001, weil betmaster lokal auf
    # 5000 liegt und beide gleichzeitig offen sein sollen.
    app.run(host="127.0.0.1", port=5001, debug=True)
