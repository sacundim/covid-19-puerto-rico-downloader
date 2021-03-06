FROM python:3.7-slim AS base

FROM base AS poetry
RUN pip install poetry==1.0.10


FROM poetry AS requirements
ENV POETRY_VIRTUALENVS_CREATE=false
WORKDIR /covid-19-puerto-rico
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt >requirements.txt


FROM requirements AS build
WORKDIR /covid-19-puerto-rico
COPY src src
RUN poetry build


FROM base as app

# Install various prerequistes for our scripts
RUN apt-get update
RUN apt-get install -y wget bzip2 time
RUN python3 -m pip install pipx
RUN pipx install awscli
RUN pipx install csv2parquet
RUN pipx inject csv2parquet pyarrow

# Debian Buster comes with jq 1.5, we want 1.6:
ARG JQ16_URL="https://github.com/stedolan/jq/releases/download/jq-1.6/jq-linux64"
ARG JQ16_SHA256="af986793a515d500ab2d35f8d2aecd656e764504b789b66d7e1a0b727a124c44"
RUN wget -O /usr/local/bin/jq "${JQ16_URL}"
RUN [ "${JQ16_SHA256}  /usr/local/bin/jq" = "$(sha256sum /usr/local/bin/jq)" ]
RUN chmod +x /usr/local/bin/jq

# Install our stuff proper
WORKDIR /covid-19-puerto-rico
COPY --from=requirements /covid-19-puerto-rico/requirements.txt ./
RUN pip install -r requirements.txt \
 && rm requirements.txt
COPY --from=build /covid-19-puerto-rico/dist/covid_19_puerto_rico_downloader-*.whl .

# `covid19datos.salud.gov.pr` has a sketchy SSL certificate,
# so we install the intermediate cert that it needs:
COPY certs/*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates
ENV REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"

RUN pip install covid_19_puerto_rico_downloader-*.whl \
 && rm covid_19_puerto_rico_downloader-*.whl
RUN mkdir -p \
    s3-bucket-sync/covid-19-puerto-rico-data \
    scripts \
    tmp
COPY scripts/*.sh ./scripts/
RUN chmod +x ./scripts/*.sh

ENV PATH=/root/.local/bin:/covid-19-puerto-rico/scripts:$PATH
ENTRYPOINT ["run-and-sync.sh"]