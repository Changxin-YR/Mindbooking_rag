[CmdletBinding()]
param([string]$BaseUrl = 'http://localhost:8000')

$ErrorActionPreference = 'Stop'
$json = @{ author_id = 'author-seed'; title = '长夜微光'; synopsis = '开发环境示例作品' } | ConvertTo-Json
$book = Invoke-RestMethod -Method Post -Uri "$BaseUrl/writer/api/v1/books" -ContentType 'application/json' -Body $json
$volume = Invoke-RestMethod -Method Post -Uri "$BaseUrl/writer/api/v1/books/$($book.id)/volumes" -ContentType 'application/json' -Body (@{ number = 1; title = '第一卷' } | ConvertTo-Json)
$chapter = Invoke-RestMethod -Method Post -Uri "$BaseUrl/writer/api/v1/volumes/$($volume.id)/chapters" -ContentType 'application/json' -Body (@{ number = 1; title = '灯火照见旧山河'; commercial_policy = 'FREE' } | ConvertTo-Json)
$draft = Invoke-RestMethod -Method Post -Uri "$BaseUrl/writer/api/v1/chapters/$($chapter.id)/drafts" -ContentType 'application/json' -Body (@{ content = '开发环境示例正文。'; save_mode = 'MANUAL' } | ConvertTo-Json)
$version = Invoke-RestMethod -Method Post -Uri "$BaseUrl/writer/api/v1/chapters/$($chapter.id)/versions" -ContentType 'application/json' -Body (@{ snapshot_id = $draft.id } | ConvertTo-Json)
$submission = Invoke-RestMethod -Method Post -Uri "$BaseUrl/writer/api/v1/books/$($book.id)/first-listing-submissions" -ContentType 'application/json' -Body (@{ fixed_version_ids = @($version.id) } | ConvertTo-Json)
Invoke-RestMethod -Method Post -Uri "$BaseUrl/admin/api/v1/reviews/$($submission.id)/decisions" -ContentType 'application/json' -Body (@{ reviewer_id = 'staff-seed'; decision = 'APPROVE'; actor_type = 'human' } | ConvertTo-Json) | Out-Null
Write-Host "Seeded book $($book.id) and chapter $($chapter.id)."
