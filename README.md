# ckanext-datagovau

This CKAN Extension customises a CKAN instance for the hosting of data.gov.au.

## Installation

1. Install the project using standard
   [CDM](https://github.com/DataShades/ckan-deps-installer) workflow
   ```sh
   make prepare
   make full-upgrade
   ```

2. The project uses PostgreSQL extensions for identifying similar
   datasets. Setup them by running two following commands in PostgreSQL CLI:
   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
   ```

3. Optional. Build LGA cache for spatial search widget, to make it faster
   ```sh
   ckan dga maintain fetch-lga
   ```

4. Optional. Create metaphone index for `package.title`. It's used to improve
   performance of similar dataset detection
   ```sql
   CREATE INDEX idx_package_title_dmetaphone ON package (dmetaphone(title));
   ```


## Development

1. Instal dev-requirements:
   ```sh
   make prepare
   make full-upgrade develop=1
   pip install -e '.[dev]'
   ```

2. Initialize git-hooks:
   ```sh
   pip install pre-commit
   pre-commit install
   ```

3. Perform all non-standard steps(like setting up PostgreSQL extensions) from
   [installation](#markdown-header-installation) section

## Testing

### Unittests

Run tests using standard CKAN test settings

```sh
pytest
```

### E2e tests

Start the test application to handle requests from e2e test engine

```sh
make test-server
```

In a separate terminal run the tests

```sh
pytest -m playwright
```
