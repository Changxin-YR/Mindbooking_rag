[CmdletBinding()]
param(
    [string]$BaseUrl = 'https://1.14.148.15/books',
    [Parameter(Mandatory = $true)][string]$StaffCode,
    [Parameter(Mandatory = $true)][string]$StaffPassword,
    [string]$PhonePrefix = '1399000'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$skipCert = @{ SkipCertificateCheck = $true }

# These editions are public-domain Project Gutenberg texts. Modern catalogue entries stay metadata-only.
$readable = @(
    @{ title='了不起的盖茨比'; seedIndex=2; author='F. Scott Fitzgerald'; url='https://www.gutenberg.org/files/64317/64317-0.txt'; category='美国文学'; tags=@('经典','爵士时代','出版1925'); lifecycle='COMPLETED' },
    @{ title='傲慢与偏见'; seedIndex=4; author='Jane Austen'; url='https://www.gutenberg.org/files/1342/1342-0.txt'; category='英国文学'; tags=@('经典','爱情','出版1813'); lifecycle='COMPLETED' },
    @{ title='简爱'; seedIndex=5; author='Charlotte Bronte'; url='https://www.gutenberg.org/files/1260/1260-0.txt'; category='英国文学'; tags=@('经典','成长','哥特','出版1847'); lifecycle='COMPLETED' },
    @{ title='呼啸山庄'; seedIndex=6; author='Emily Bronte'; url='https://www.gutenberg.org/files/768/768-0.txt'; category='英国文学'; tags=@('经典','哥特','复仇','出版1847'); lifecycle='COMPLETED' },
    @{ title='罪与罚'; seedIndex=9; author='Fyodor Dostoevsky'; url='https://www.gutenberg.org/files/2554/2554-0.txt'; category='俄国文学'; tags=@('经典','心理小说','出版1866'); lifecycle='COMPLETED' },
    @{ title='爱丽丝漫游奇境'; seedIndex=35; author='Lewis Carroll'; url='https://www.gutenberg.org/files/11/11-0.txt'; category='世界文学'; tags=@('经典','幻想','出版1865'); lifecycle='COMPLETED' },
    @{ title='弗兰肯斯坦'; seedIndex=36; author='Mary Shelley'; url='https://www.gutenberg.org/files/84/84-0.txt'; category='哥特文学'; tags=@('经典','科幻','出版1818'); lifecycle='COMPLETED' },
    @{ title='双城记'; seedIndex=37; author='Charles Dickens'; url='https://www.gutenberg.org/files/98/98-0.txt'; category='英国文学'; tags=@('经典','历史小说','出版1859'); lifecycle='COMPLETED' },
    @{ title='德古拉'; seedIndex=38; author='Bram Stoker'; url='https://www.gutenberg.org/files/345/345-0.txt'; category='哥特文学'; tags=@('经典','吸血鬼','出版1897'); lifecycle='COMPLETED' },
    @{ title='基督山伯爵'; seedIndex=39; author='Alexandre Dumas'; url='https://www.gutenberg.org/files/1184/1184-0.txt'; category='历史小说'; tags=@('经典','复仇','出版1844'); lifecycle='COMPLETED' }
)

function Invoke-JsonApi([string]$Method, [string]$Path, [object]$Body = $null, [hashtable]$Headers = @{}) {
    $params = @{ Method = $Method; Uri = ($BaseUrl.TrimEnd('/') + $Path); Headers = $Headers; ErrorAction = 'Stop' } + $skipCert
    if ($null -ne $Body) {
        $params.ContentType = 'application/json'
        $params.Body = ($Body | ConvertTo-Json -Depth 8 -Compress)
    }
    Invoke-RestMethod @params
}

function Get-GutenbergChapters([string]$text) {
    $start = $text.IndexOf('*** START OF THE PROJECT GUTENBERG EBOOK')
    $end = $text.IndexOf('*** END OF THE PROJECT GUTENBERG EBOOK')
    if ($start -ge 0) { $text = $text.Substring($start) }
    if ($end -gt 0) { $text = $text.Substring(0, $text.IndexOf("`n", $end)) }
    $matches = [regex]::Matches($text, '(?im)^\s*(?:chapter\s+[IVXLCDM0-9]+[^\r\n]*|letter\s+\d+[^\r\n]*|[IVXLCDM]{1,4})\s*$')
    $chapters = @()
    for ($i = 0; $i -lt $matches.Count; $i++) {
        $heading = $matches[$i].Value.Trim() -replace '\s+', ' '
        $contentStart = $matches[$i].Index + $matches[$i].Length
        $contentEnd = if ($i + 1 -lt $matches.Count) { $matches[$i + 1].Index } else { $text.Length }
        $content = $text.Substring($contentStart, $contentEnd - $contentStart).Trim()
        if ($content.Length -lt 120) { continue }
        $chapters += [pscustomobject]@{ title = $heading; content = $content }
    }
    if ($chapters.Count -eq 0) {
        $body = $text.Trim()
        if ($body.Length -lt 120) { throw '公开文本没有可读正文' }
        return @([pscustomobject]@{ title = '正文'; content = $body })
    }
    return $chapters
}

function Get-OrCreateAccount([int]$seedIndex) {
    $phone = "$PhonePrefix$('{0:D4}' -f $seedIndex)"
    $password = "BookSeed#$($seedIndex)2026"
    $accountId = $null
    try { $created = Invoke-JsonApi 'Post' '/api/v1/iam/accounts' @{ phone = $phone; password = $password }; $accountId = $created.account_id } catch { }
    $session = Invoke-JsonApi 'Post' '/api/v1/iam/sessions' @{ phone = $phone; password = $password }
    if (-not $accountId) { $accountId = $session.account_id }
    return @{ session = $session; account_id = $accountId; headers = @{ Authorization = "Bearer $($session.access_token)" } }
}

$staff = Invoke-JsonApi 'Post' '/admin/api/v1/auth/staff/sessions' @{ employee_code = $StaffCode; password = $StaffPassword }
$staffHeaders = @{ Authorization = "Bearer $($staff.access_token)" }

foreach ($bookInfo in $readable) {
    Write-Host "准备正文：$($bookInfo.title)"
    $account = Get-OrCreateAccount $bookInfo.seedIndex
    $authorHeaders = $account.headers
    try {
        $profile = Invoke-JsonApi 'Get' '/writer/api/v1/author/profile' $null $authorHeaders
    } catch {
        $profile = Invoke-JsonApi 'Post' '/writer/api/v1/author/profiles' @{ account_id = $account.account_id; pen_name = $bookInfo.author } $authorHeaders
    }
    $writerBooks = Invoke-JsonApi 'Get' ("/writer/api/v1/books?author_id=" + [uri]::EscapeDataString($profile.id)) $null $authorHeaders
    $book = @($writerBooks | Where-Object { $_.title -eq $bookInfo.title }) | Select-Object -First 1
    $isNew = $null -eq $book

    if ($isNew) {
        $synopsis = "公开领域完整文本，来源：Project Gutenberg（$($bookInfo.url)）。"
        $book = Invoke-JsonApi 'Post' '/writer/api/v1/books' @{ author_id = $profile.id; title = $bookInfo.title; synopsis = $synopsis; channel = 'UNSPECIFIED'; category = $bookInfo.category; tags = $bookInfo.tags } $authorHeaders
    } else {
        $detail = Invoke-JsonApi 'Get' ("/api/v1/books/$($book.id)")
        if (@($detail.chapters).Count -gt 1) { Write-Host "SKIP 已有正文：$($bookInfo.title)"; continue }
    }

    $text = (Invoke-WebRequest -Uri $bookInfo.url -UseBasicParsing).Content
    $chapters = @(Get-GutenbergChapters $text)
    $volume = Invoke-JsonApi 'Post' "/writer/api/v1/books/$($book.id)/volumes" @{ number = 2; title = '正文' } $authorHeaders
    $versionIds = @()
    for ($i = 0; $i -lt $chapters.Count; $i++) {
        $chapter = Invoke-JsonApi 'Post' "/writer/api/v1/volumes/$($volume.id)/chapters" @{ number = $i + 1; title = $chapters[$i].title; commercial_policy = 'FREE' } $authorHeaders
        $snapshot = Invoke-JsonApi 'Post' "/writer/api/v1/chapters/$($chapter.id)/drafts" @{ content = $chapters[$i].content; save_mode = 'MANUAL' } $authorHeaders
        $version = Invoke-JsonApi 'Post' "/writer/api/v1/chapters/$($chapter.id)/versions" @{ snapshot_id = $snapshot.id } $authorHeaders
        $versionIds += $version.id
        Start-Sleep -Milliseconds 40
    }
    if ($isNew) {
        $submission = Invoke-JsonApi 'Post' "/writer/api/v1/books/$($book.id)/first-listing-submissions" @{ fixed_version_ids = $versionIds } $authorHeaders
    } else {
        $submission = Invoke-JsonApi 'Post' "/writer/api/v1/books/$($book.id)/chapter-submissions" @{ fixed_version_ids = $versionIds } $authorHeaders
    }
    Invoke-JsonApi 'Post' "/admin/api/v1/reviews/$($submission.id)/decisions" @{ reviewer_id = $staff.staff_id; decision = 'APPROVE'; actor_type = 'human' } $staffHeaders | Out-Null
    Invoke-JsonApi 'Patch' "/admin/api/v1/books/$($book.id)/lifecycle" @{ lifecycle = $bookInfo.lifecycle } $staffHeaders | Out-Null
    Write-Host "DONE $($bookInfo.title): $($chapters.Count) 章"
}
