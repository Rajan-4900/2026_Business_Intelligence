# -------------------------------------------------
# Dockerfile – builds a container that runs Daphne (ASGI)
# -------------------------------------------------
FROM python:3.12-slim

# System libs needed for psycopg2 (PostgreSQL driver) and WeasyPrint (PDF reports:
# Pango/HarfBuzz for text layout, fontconfig for fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Working directory inside the container
WORKDIR /app

# Copy the whole project into the image
COPY . /app

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Collect static files (required for Django)
ENV DJANGO_SETTINGS_MODULE=crowd_heatmap_project.settings
RUN python manage.py collectstatic --noinput

# Render injects PORT at runtime; default to 8000 at build time
EXPOSE 8000

# Apply migrations (the SQLite file is not in the image; this also creates the report table),
# then start Daphne (ASGI server) – shell form so $PORT is expanded at runtime
CMD python manage.py migrate --noinput && daphne -b 0.0.0.0 -p ${PORT:-8000} crowd_heatmap_project.asgi:application
