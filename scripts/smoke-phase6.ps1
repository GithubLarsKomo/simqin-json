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

$schemas = Invoke-RestMethod -Uri "$ApiBase/api/v1/content/schemas" -Method Get
if (-not $schemas) {
    throw 'Phase 6 schema catalog returned no content.'
}
Write-Host "[OK] Phase 6 schema catalog"

$payload = @{
    root_object_ids = @('tpl-smoke')
    revision_mode = 'pinned'
    pinned_revisions = @{
        'tpl-smoke' = 1
    }
    config_values = @{
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
Write-Host 'Phase 6 smoke test PASSED.'
