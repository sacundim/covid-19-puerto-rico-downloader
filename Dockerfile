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
RUN apt-get update
RUN apt-get install -y bzip2 time libyajl2
RUN python3 -m pip install pipx
RUN pipx install awscli
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