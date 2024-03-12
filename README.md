# Tensorflow converter

Converts models from Tensorflow to Tensorflow.js.

```
pip install -r requirements.txt
python3 app.py
celery -A celery_worker.celery worker --loglevel=info
```

## Production

```
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## Deploy
Use at least 2048 mb ram:

```
fly scale memory 2048 -a tensorflow-converter
```

```
flyctl deploy
```