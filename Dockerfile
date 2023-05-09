# Start from a Python 3.8 image
FROM python:3.8-slim-buster

# Set a directory for the app
WORKDIR /usr/src/app

# Copy all application files into the container
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port gunicorn will listen on
EXPOSE 8000

# Finally, run gunicorn.
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]

