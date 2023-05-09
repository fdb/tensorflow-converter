# Tensorflow converter

Converts models from Tensorflow to Tensorflow.js.

```
pip install -r requirements.txt
python3 app.py
```

## Production

```
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```


