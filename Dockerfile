# Start from a Python 3.11 image
FROM python:3.11-slim-buster

# Set a directory for the app
WORKDIR /usr/src/app

# Install supervisord
RUN apt-get update && apt-get install -y supervisor && rm -rf /var/lib/apt/lists/*

# Copy all application files into the container
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port gunicorn will listen on
EXPOSE 8000

# Copy supervisord configuration file
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Start processes using supervisord
CMD ["/usr/bin/supervisord"]
