FROM python:3.9-slim

# Set workdir
WORKDIR /workspace

# Copy requirements core files and install
COPY requirements/requirements_core.txt .
# Install
RUN pip install -r requirements_core.txt

# Copy requirements component files and install
COPY requirements/requirements_component.txt .
RUN pip install -r requirements_component.txt

# Copy requirements db files and install
COPY requirements/requirements_db.txt .
RUN pip install -r requirements_db.txt
# Copy the rest
COPY . /workspace

EXPOSE 8005