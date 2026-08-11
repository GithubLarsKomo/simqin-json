$ErrorActionPreference = 'Stop'

$ApiBase = $env:SIMQIN_API_BASE
if ([string]::IsNullOrWhiteSpace($ApiBase)) {
    $ApiBase = 'http://localhost:8080'
}

Write-Host "SIMQIN Phase 6 smoke test against $ApiBase"

$health = Invoke-RestMethod -Uri "$ApiBase/health" -Method Get
if ($health.status -ne 'ok') {
    throw "API health check failed: $($health | ConvertTo-Json -Depth 8)"
}
Write-Host "[OK] API health"

$session = Invoke-RestMethod -Uri "$ApiBase/api/v1/session" -Method Get
if ([string]::IsNullOrWhiteSpace($session.user_id) -or $session.role -notin @('author', 'reviewer', 'approver')) {
    throw "Phase 6 trusted session is invalid: $($session | ConvertTo-Json -Depth 8)"
}
Write-Host "[OK] Trusted session: $($session.user_id) / $($session.role)"

$schemas = Invoke-RestMethod -Uri "$ApiBase/api/v1/content/schemas" -Method Get
if (-not $schemas) {
    throw 'Phase 6 schema catalog returned no content.'
}
Write-Host "[OK] Phase 6 schema catalog"

$canonicalCatalog = Invoke-RestMethod -Uri "$ApiBase/api/v1/content/canonical-snapshots" -Method Get
if ($null -eq $canonicalCatalog.count -or $null -eq $canonicalCatalog.snapshots) {
    throw "Canonical source catalog returned an invalid contract: $($canonicalCatalog | ConvertTo-Json -Depth 8)"
}
Write-Host "[OK] Trusted canonical source catalog: $($canonicalCatalog.count) snapshot(s)"

$translationCatalog = Invoke-RestMethod -Uri "$ApiBase/api/v1/translations/variants" -Method Get
if ($null -eq $translationCatalog.count -or $null -eq $translationCatalog.variants) {
    throw "Translation catalog returned an invalid contract: $($translationCatalog | ConvertTo-Json -Depth 8)"
}
Write-Host "[OK] Persistent translation catalog: $($translationCatalog.count) variant(s)"

$payload = @{
    root_object_ids = @('tpl-smoke')
    revision_mode = 'pinned'
    pinned_revisions = @{
        'tpl-smoke' = 1
    }
    slot_values = @{
        analyte = 'ANA'
        sample_type = 'Serum'
    }
    objects = @(
        @{
            id = 'tpl-smoke'
            type = 'template'
            section_type = 'intended-use'
            canonical_language = 'de-DE'
            status = 'approved'
            current_revision = 1
            revisions = @(
                @{
                    object_id = 'tpl-smoke'
                    revision = 1
                    canonical_content = 'Bestimmung von {{analyte}} in {{sample_type}}.'
                    sentence_segments = @(
                        @{
                            segment_id = 'seg-smoke-1'
                            segment_type = 'sentence'
                            source_text = 'Bestimmung von {{analyte}} in {{sample_type}}.'
                            source_revision = 1
                        }
                    )
                    slots = @(
                        @{
                            slot_id = 'analyte'
                            type = 'analyte'
                            required = $true
                        },
                        @{
                            slot_id = 'sample_type'
                            type = 'sample-type'
                            required = $true
                        }
                    )
                    approval_status = 'approved'
                }
            )
        }
    )
} | ConvertTo-Json -Depth 20

$result = Invoke-RestMethod `
    -Uri "$ApiBase/api/v1/content/resolve" `
    -Method Post `
    -ContentType 'application/json' `
    -Body $payload

if (-not $result.blocks -or $result.blocks.Count -lt 1) {
    throw 'Resolver returned no blocks.'
}

$rendered = $result.blocks[0].rendered_content
if ($rendered -notmatch 'ANA' -or $rendered -notmatch 'Serum') {
    throw "Resolver did not render expected slot values: $rendered"
}

if ([string]::IsNullOrWhiteSpace($result.checksum)) {
    throw 'Resolver result has no checksum.'
}

$fatal = @($result.findings | Where-Object { $_.severity -in @('ERROR', 'FATAL') })
if ($fatal.Count -gt 0) {
    throw "Resolver returned blocking findings: $($fatal | ConvertTo-Json -Depth 8)"
}

Write-Host "[OK] Phase 6 resolver via API gateway"
Write-Host "[OK] Rendered: $rendered"
Write-Host "[OK] Checksum: $($result.checksum)"

$migrationId = "smoke-$([guid]::NewGuid().ToString('N'))"
$reviewBody = @{
    created_by = 'smoke-author'
    reviewer = 'smoke-reviewer'
    decision = 'approved'
    comment = 'Automated Phase 6 smoke review.'
} | ConvertTo-Json

$createdDecision = Invoke-RestMethod `
    -Uri "$ApiBase/api/v1/reviews/migrations/$migrationId/decisions" `
    -Method Post `
    -ContentType 'application/json' `
    -Body $reviewBody

if ($createdDecision.migration_id -ne $migrationId -or $createdDecision.decision -ne 'approved') {
    throw "Persistent review write returned unexpected content: $($createdDecision | ConvertTo-Json -Depth 8)"
}

$reviewHistory = Invoke-RestMethod `
    -Uri "$ApiBase/api/v1/reviews/migrations/$migrationId/decisions" `
    -Method Get

if ($reviewHistory.count -ne 1 -or $reviewHistory.decisions[0].decision_id -ne $createdDecision.decision_id) {
    throw "Persistent review read-back failed: $($reviewHistory | ConvertTo-Json -Depth 8)"
}

Write-Host "[OK] Persistent review write/read via API gateway"
Write-Host "[OK] Review decision: $($createdDecision.decision_id)"
Write-Host 'Phase 6 smoke test PASSED.'
