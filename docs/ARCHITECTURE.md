# Architecture

Das Projekt startet bewusst als pragmatischer Microservice-Schnitt:

- API Gateway für Browser und externe Clients
- Worker für Parser/Validator/Mapper
- Frontend als eigenständiger Browser-Service

Parser, Validator und Mapper liegen zunächst im Worker, können aber später in getrennte Container ausgelagert werden.

## Erweiterung zu echten Microservices

Später kann `worker` aufgeteilt werden in:

- `xml-parse-service`
- `validation-service`
- `mapping-service`
- `schema-service`
- `export-service`

Die API bleibt dann stabil und delegiert intern über REST, gRPC oder Queue.
