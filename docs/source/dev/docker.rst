Development with Docker Container
=================================

If you want to develop on Windows (or Mac) you can use a Docker container
with Debian.

.. note::

   It is even possible to build and run your container inside WSL. In this case
   please make sure that you have the **Docker Desktop App** for Windows
   running beside your WSL docker service! Otherwise the port forwarding will not work
   and your web2py project will not be available via localhost.

On your machine create a project folder `eden-dev`. Create the following two
files in it:

.. code-block:: dockerfile
  :caption: Dockerfile

	FROM debian:13

	ENV DEBIAN_FRONTEND=noninteractive
	ENV LANG=C.UTF-8

	RUN apt-get update && apt-get install -y \
			python3 \
			python3-pip \
			git \
			nano \
			vim \
			curl \
			wget \
			build-essential \
			openssl \
			libxml2 \
			libxslt1.1 \
			libgeos-c1v5 \
			libpq5 \
			libjpeg62-turbo \
			zlib1g \
			libfreetype6 \
			&& rm -rf /var/lib/apt/lists/*

	RUN pip3 install --break-system-packages --only-binary=:all: \
			lxml \
			python-dateutil \
			pyparsing \
			requests \
			xlrd \
			xlwt \
			openpyxl \
			reportlab \
			shapely \
			geopy \
			qrcode \
			docx-mailmerge \
			psycopg2-binary \
			sphinx \
			sphinx-rtd-theme

	# Workspace
	WORKDIR /workspace

	RUN git clone https://github.com/web2py/web2py.git && \
			cd web2py && \
			git reset --hard  d6dcbef && \
			git submodule update --init --recursive

	# Generating self-signed certificate
	RUN openssl req -x509 -newkey rsa:4096 \
		-keyout /workspace/key.pem -out /workspace/cert.pem -days 365 -nodes \
		-subj "/C=US/ST=State/L=City/O=Organization/OU=Department/CN=localhost.local"

	EXPOSE 8000

.. code-block:: yaml
	:caption: docker-compose.yml

	services:
		eden:
			build: .
			container_name: eden-dev
			volumes:
				- ./eden:/workspace/eden
			ports:
				- "18000:8000"
			tty: true
			stdin_open: true

Afterwards clone the Eden repo into your folder:

.. code-block:: console

	git clone https://github.com/sahana/eden.git

Your folder should now look like this:

.. code-block:: text

   Your folder/
   ├── eden/	# The eden repository must be cloned here
   ├── Dockerfile
   └── docker-compose.yml

Now from inside of your folder you can build your image and your container:

.. code-block:: console

   docker-compose build --no-cache
   docker-compose up -d

The container is now running. Next time to start your container you only
have to type:

.. code-block:: console

   docker start eden-dev

You can enter your running container with:

.. code-block:: console

   docker exec -it eden-dev bash

The folder `eden` from your project folder is mounted on your container to
`/workspace/eden`. The changes you make inside the container to the files and folders
here will also change the files in your local eden folder and the other way around.
This way you can work locally with the IDE of your choice on the Eden project.

From here you can follow the main documentation for configuring Eden as a web2py application as described :ref:`here <entrance-docker-setup>`.

.. note::

   Eden is available via browser on http://localhost:18000 if you're using this
   container setup to keep port 8000 available to other projects! Keep it in mind
   when you follow the rest of the configuration documentation.

