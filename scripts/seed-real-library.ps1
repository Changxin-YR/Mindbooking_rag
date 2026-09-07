[CmdletBinding()]
param(
    [string]$BaseUrl = 'https://1.14.148.15/books',
    [Parameter(Mandatory = $true)][string]$StaffCode,
    [Parameter(Mandatory = $true)][string]$StaffPassword,
    [string]$PhonePrefix = '1399000'
)

$ErrorActionPreference = 'Stop'
$skipCert = @{ SkipCertificateCheck = $true }

$books = @(
    @{ title='1984'; author='George Orwell'; category='反乌托邦'; tags=@('经典','政治寓言','出版1949'); lifecycle='COMPLETED'; summary='英国作家 George Orwell 的反乌托邦小说，描写极权社会、全面监控与思想控制，1949 年出版并被公认为现代文学经典。'; source='https://en.wikipedia.org/wiki/Nineteen_Eighty-Four' },
    @{ title='了不起的盖茨比'; author='F. Scott Fitzgerald'; category='美国文学'; tags=@('经典','爵士时代','出版1925'); lifecycle='COMPLETED'; summary='美国作家 F. Scott Fitzgerald 的小说，以爵士时代长岛为背景，通过 Nick Carraway 与神秘富豪 Jay Gatsby 的交往书写爱情与阶层。'; source='https://en.wikipedia.org/wiki/The_Great_Gatsby' },
    @{ title='杀死一只知更鸟'; author='Harper Lee'; category='美国文学'; tags=@('经典','成长','普利策奖','出版1960'); lifecycle='COMPLETED'; summary='Harper Lee 的南方哥特小说，以儿童视角观察种族正义与成长，出版后获得普利策奖并成为美国现代文学经典。'; source='https://en.wikipedia.org/wiki/To_Kill_a_Mockingbird' },
    @{ title='傲慢与偏见'; author='Jane Austen'; category='英国文学'; tags=@('经典','爱情','出版1813'); lifecycle='COMPLETED'; summary='Jane Austen 的礼仪喜剧小说，围绕 Elizabeth Bennet 的成长与判断展开，探讨偏见、阶层和真正的善良。'; source='https://en.wikipedia.org/wiki/Pride_and_Prejudice' },
    @{ title='简爱'; author='Charlotte Brontë'; category='英国文学'; tags=@('经典','成长','哥特','出版1847'); lifecycle='COMPLETED'; summary='Charlotte Brontë 的成长小说，讲述 Jane Eyre 从孤儿到独立女性的经历，以及她与 Rochester 之间的感情。'; source='https://en.wikipedia.org/wiki/Jane_Eyre' },
    @{ title='呼啸山庄'; author='Emily Brontë'; category='英国文学'; tags=@('经典','哥特','复仇','出版1847'); lifecycle='COMPLETED'; summary='Emily Brontë 唯一的小说，描写 Heathcliff 与 Earnshaw、Linton 两家之间纠缠的爱、占有、复仇与和解。'; source='https://en.wikipedia.org/wiki/Wuthering_Heights' },
    @{ title='小王子'; author='Antoine de Saint-Exupéry'; category='世界文学'; tags=@('经典','寓言','出版1943'); lifecycle='COMPLETED'; summary='法国作家与飞行员 Antoine de Saint-Exupéry 创作的寓言小说，通过小王子访问不同星球讨论孤独、友谊、爱与失去。'; source='https://en.wikipedia.org/wiki/The_Little_Prince' },
    @{ title='百年孤独'; author='Gabriel García Márquez'; category='拉美文学'; tags=@('经典','魔幻现实主义','出版1967'); lifecycle='COMPLETED'; summary='Gabriel García Márquez 的代表作，讲述 Buendía 家族在虚构小镇 Macondo 跨越数代的命运，被誉为西语文学的重要作品。'; source='https://en.wikipedia.org/wiki/One_Hundred_Years_of_Solitude' },
    @{ title='罪与罚'; author='Fyodor Dostoevsky'; category='俄国文学'; tags=@('经典','心理小说','出版1866'); lifecycle='COMPLETED'; summary='Dostoevsky 的长篇小说，围绕青年 Raskolnikov 的犯罪、良知与救赎展开，被视为世界文学名著。'; source='https://en.wikipedia.org/wiki/Crime_and_Punishment' },
    @{ title='The Hobbit'; author='J. R. R. Tolkien'; category='奇幻'; tags=@('经典','冒险','出版1937'); lifecycle='COMPLETED'; summary='J. R. R. Tolkien 的奇幻小说，讲述 Bilbo Baggins 离开家园、参与远征并成长为冒险者的故事，出版后广受好评。'; source='https://en.wikipedia.org/wiki/The_Hobbit' },
    @{ title='魔戒'; author='J. R. R. Tolkien'; category='奇幻'; tags=@('经典','史诗奇幻','出版1954'); lifecycle='COMPLETED'; summary='Tolkien 创作的史诗奇幻小说，设定于中土世界，围绕魔戒远征与对抗黑暗力量展开，是世界畅销书之一。'; source='https://en.wikipedia.org/wiki/The_Lord_of_the_Rings' },
    @{ title='沙丘'; author='Frank Herbert'; category='科幻'; tags=@('经典','太空歌剧','出版1965'); lifecycle='COMPLETED'; summary='Frank Herbert 的史诗科幻小说，以 Arrakis 星球、香料资源和家族政治为核心，获得雨果奖与星云奖。'; source='https://en.wikipedia.org/wiki/Dune_(novel)' },
    @{ title='基地'; author='Isaac Asimov'; category='科幻'; tags=@('经典','太空歌剧','出版1951'); lifecycle='COMPLETED'; summary='Isaac Asimov 的科幻小说，讲述心理史学家 Hari Seldon 预见银河帝国衰落后建立基地保存文明的故事。'; source='https://en.wikipedia.org/wiki/Foundation_(Asimov_novel)' },
    @{ title='美丽新世界'; author='Aldous Huxley'; category='反乌托邦'; tags=@('经典','社会寓言','出版1932'); lifecycle='COMPLETED'; summary='Aldous Huxley 描写未来世界以生物工程、消费和条件反射维持秩序，并通过局外人 John 质疑这套乌托邦制度。'; source='https://en.wikipedia.org/wiki/Brave_New_World' },
    @{ title='华氏451度'; author='Ray Bradbury'; category='反乌托邦'; tags=@('经典','科幻','出版1953'); lifecycle='COMPLETED'; summary='Ray Bradbury 的反乌托邦小说，描写禁书社会中消防员 Guy Montag 从焚书者转向保存知识的过程。'; source='https://en.wikipedia.org/wiki/Fahrenheit_451' },
    @{ title='麦田里的守望者'; author='J. D. Salinger'; category='成长小说'; tags=@('经典','成长','出版1951'); lifecycle='COMPLETED'; summary='J. D. Salinger 的成长小说，记录 Holden Caulfield 离校后的漫游与内心挣扎，长期被视为美国文学经典。'; source='https://en.wikipedia.org/wiki/The_Catcher_in_the_Rye' },
    @{ title='追风筝的人'; author='Khaled Hosseini'; category='世界文学'; tags=@('畅销','成长','阿富汗','出版2003'); lifecycle='COMPLETED'; summary='Khaled Hosseini 的小说，以阿富汗社会变迁为背景，讲述 Amir 的友谊、背叛与赎罪。'; source='https://en.wikipedia.org/wiki/The_Kite_Runner' },
    @{ title='偷书贼'; author='Markus Zusak'; category='历史小说'; tags=@('畅销','二战','出版2005'); lifecycle='COMPLETED'; summary='Markus Zusak 的历史小说，背景为二战时期的纳粹德国，以死亡为叙述者讲述 Liesel 与书籍的故事。'; source='https://en.wikipedia.org/wiki/The_Book_Thief' },
    @{ title='玫瑰之名'; author='Umberto Eco'; category='历史小说'; tags=@('经典','悬疑','出版1980'); lifecycle='COMPLETED'; summary='Umberto Eco 的历史推理小说，故事发生在 1327 年意大利修道院，结合谋杀谜案、中世纪思想与符号学。'; source='https://en.wikipedia.org/wiki/The_Name_of_the_Rose' },
    @{ title='老人与海'; author='Ernest Hemingway'; category='世界文学'; tags=@('经典','诺贝尔文学奖','出版1952'); lifecycle='COMPLETED'; summary='Ernest Hemingway 的中篇小说，讲述老渔夫 Santiago 与巨型马林鱼进行漫长搏斗的故事。'; source='https://en.wikipedia.org/wiki/The_Old_Man_and_the_Sea' },
    @{ title='红楼梦'; author='曹雪芹'; category='中国古典'; tags=@('四大名著','古典文学','清代'); lifecycle='COMPLETED'; summary='曹雪芹创作的章回体小说，围绕贾宝玉、林黛玉与薛宝钗以及贾府兴衰展开，被列为中国四大名著之一。'; source='https://zh.wikipedia.org/wiki/红楼梦' },
    @{ title='西游记'; author='吴承恩'; category='中国古典'; tags=@('四大名著','神话','明代'); lifecycle='COMPLETED'; summary='吴承恩名义下成书的明代神魔小说，讲述唐僧师徒西天取经的冒险，被视为中国古典文学名著。'; source='https://zh.wikipedia.org/wiki/西游记' },
    @{ title='三国演义'; author='罗贯中'; category='中国古典'; tags=@('四大名著','历史小说','明代'); lifecycle='COMPLETED'; summary='罗贯中编撰的历史演义小说，叙述东汉末年至西晋统一之间的战争、政治与人物传奇。'; source='https://zh.wikipedia.org/wiki/三国演义' },
    @{ title='水浒传'; author='施耐庵'; category='中国古典'; tags=@('四大名著','英雄传奇','明代'); lifecycle='COMPLETED'; summary='中国古典小说，描写梁山好汉聚义及其命运，被认为是最早的白话长篇小说经典之一。'; source='https://zh.wikipedia.org/wiki/水浒传' },
    @{ title='活着'; author='余华'; category='中国当代'; tags=@('当代文学','现实主义','出版1993'); lifecycle='COMPLETED'; summary='余华创作的长篇小说，讲述徐福贵在时代变迁中经历家庭与个人命运起伏的故事。'; source='https://en.wikipedia.org/wiki/To_Live_(novel)' },
    @{ title='平凡的世界'; author='路遥'; category='中国当代'; tags=@('当代文学','现实主义','茅盾文学奖'); lifecycle='COMPLETED'; summary='路遥的长篇小说，以孙少安、孙少平兄弟为中心，描写中国农村青年在时代变革中的奋斗与选择。'; source='https://zh.wikipedia.org/wiki/平凡的世界' },
    @{ title='白鹿原'; author='陈忠实'; category='中国当代'; tags=@('当代文学','历史小说','茅盾文学奖'); lifecycle='COMPLETED'; summary='陈忠实的长篇小说，跨越半个多世纪书写白鹿原上两个家族的纠葛与中国社会变迁，获第四届茅盾文学奖。'; source='https://en.wikipedia.org/wiki/White_Deer_Plain_(novel)' },
    @{ title='围城'; author='钱锺书'; category='中国当代'; tags=@('当代文学','讽刺','出版1947'); lifecycle='COMPLETED'; summary='钱锺书的讽刺小说，以方鸿渐的求学、婚恋和职场经历观察三十年代中国知识阶层。'; source='https://en.wikipedia.org/wiki/Fortress_Besieged' },
    @{ title='诛仙'; author='萧鼎'; category='网络玄幻'; tags=@('网络文学','仙侠','完结'); lifecycle='COMPLETED'; summary='作家萧鼎创作的仙侠网络小说，以张小凡的成长、门派纷争与情感选择为主线，属于中文网络文学代表作。'; source='https://zh.wikipedia.org/wiki/诛仙_(小说)' },
    @{ title='庆余年'; author='猫腻'; category='网络历史'; tags=@('网络文学','架空历史','完结'); lifecycle='COMPLETED'; summary='作家猫腻创作的架空历史网络小说，讲述范闲在庆国朝局与个人身世之间的成长与抉择。'; source='https://zh.wikipedia.org/wiki/庆余年' },
    @{ title='鬼吹灯'; author='天下霸唱（张牧野）'; category='网络悬疑'; tags=@('网络文学','探险','完结'); lifecycle='COMPLETED'; summary='天下霸唱创作的探险悬疑系列，围绕胡八一等人寻找古墓与秘宝展开，首部作品 2006 年上线并成为畅销网络小说。'; source='https://en.wikipedia.org/wiki/Candle_in_the_Tomb' },
    @{ title='盗墓笔记'; author='南派三叔（徐磊）'; category='网络悬疑'; tags=@('网络文学','探险','完结'); lifecycle='COMPLETED'; summary='南派三叔创作的现代探险小说系列，讲述吴邪与伙伴们探索古墓、家族历史和未知谜团的经历。'; source='https://en.wikipedia.org/wiki/Daomu_Biji' },
    @{ title='A Song of Ice and Fire'; author='George R. R. Martin'; category='史诗奇幻'; tags=@('畅销','高幻想','未完结'); lifecycle='SERIALIZING'; summary='George R. R. Martin 创作的高幻想系列，计划七卷，目前已出版五卷，作者仍在创作第六卷 The Winds of Winter。'; source='https://en.wikipedia.org/wiki/A_Song_of_Ice_and_Fire' },
    @{ title='The Kingkiller Chronicle'; author='Patrick Rothfuss'; category='奇幻'; tags=@('畅销','高幻想','暂停更新'); lifecycle='PAUSED'; summary='Patrick Rothfuss 计划创作的奇幻三部曲，目前已出版前两部，第三部尚未发行，系列处于暂停状态。'; source='https://en.wikipedia.org/wiki/The_Kingkiller_Chronicle' }
)

function Invoke-JsonApi([string]$Method, [string]$Path, [object]$Body = $null, [hashtable]$Headers = @{}) {
    $params = @{ Method = $Method; Uri = ($BaseUrl.TrimEnd('/') + $Path); Headers = $Headers; ErrorAction = 'Stop' } + $skipCert
    if ($null -ne $Body) { $params.ContentType = 'application/json'; $params.Body = ($Body | ConvertTo-Json -Depth 8 -Compress) }
    Invoke-RestMethod @params
}

$staff = Invoke-JsonApi 'Post' '/admin/api/v1/auth/staff/sessions' @{ employee_code = $StaffCode; password = $StaffPassword }
$staffHeaders = @{ Authorization = "Bearer $($staff.access_token)" }
$reviewerId = [string]$staff.staff_id

for ($index = 0; $index -lt $books.Count; $index++) {
    $bookInfo = $books[$index]
    $query = [uri]::EscapeDataString($bookInfo.title)
    $existing = Invoke-JsonApi 'Get' "/api/v1/books?q=$query"
    if ([int]$existing.total -gt 0) { Write-Host "SKIP $($bookInfo.title)"; continue }

    $phone = "$PhonePrefix$('{0:D4}' -f ($index + 1))"
    $password = "BookSeed#$($index + 1)2026"
    $account = Invoke-JsonApi 'Post' '/api/v1/iam/accounts' @{ phone = $phone; password = $password }
    $session = Invoke-JsonApi 'Post' '/api/v1/iam/sessions' @{ phone = $phone; password = $password }
    $authorHeaders = @{ Authorization = "Bearer $($session.access_token)" }
    try {
        $profile = Invoke-JsonApi 'Post' '/writer/api/v1/author/profiles' @{ account_id = $account.account_id; pen_name = $bookInfo.author } $authorHeaders
    } catch {
        $profileError = "$($_.Exception.Message) $($_.ErrorDetails.Message)"
        if ($profileError -notmatch 'AUTHOR_UNIQUENESS_CONFLICT|pen name has already been used') { throw }
        $profile = Invoke-JsonApi 'Post' '/writer/api/v1/author/profiles' @{ account_id = $account.account_id; pen_name = "$($bookInfo.author) · $($bookInfo.title) $($index + 1)" } $authorHeaders
    }
    $synopsis = "作者：$($bookInfo.author)。$($bookInfo.summary) 资料来源：$($bookInfo.source)"
    $book = Invoke-JsonApi 'Post' '/writer/api/v1/books' @{ author_id = $profile.id; title = $bookInfo.title; synopsis = $synopsis; channel = 'UNSPECIFIED'; category = $bookInfo.category; tags = $bookInfo.tags } $authorHeaders
    $volume = Invoke-JsonApi 'Post' "/writer/api/v1/books/$($book.id)/volumes" @{ number = 1; title = '公开资料' } $authorHeaders
    $chapter = Invoke-JsonApi 'Post' "/writer/api/v1/volumes/$($volume.id)/chapters" @{ number = 1; title = '作品简介与来源'; commercial_policy = 'FREE' } $authorHeaders
    $draft = Invoke-JsonApi 'Post' "/writer/api/v1/chapters/$($chapter.id)/drafts" @{ content = $synopsis; save_mode = 'MANUAL' } $authorHeaders
    $version = Invoke-JsonApi 'Post' "/writer/api/v1/chapters/$($chapter.id)/versions" @{ snapshot_id = $draft.id } $authorHeaders
    $submission = Invoke-JsonApi 'Post' "/writer/api/v1/books/$($book.id)/first-listing-submissions" @{ fixed_version_ids = @($version.id) } $authorHeaders
    Invoke-JsonApi 'Post' "/admin/api/v1/reviews/$($submission.id)/decisions" @{ reviewer_id = $reviewerId; decision = 'APPROVE'; actor_type = 'human' } $staffHeaders | Out-Null
    Invoke-JsonApi 'Patch' "/admin/api/v1/books/$($book.id)/lifecycle" @{ lifecycle = $bookInfo.lifecycle } $staffHeaders | Out-Null
    Write-Host "IMPORTED $($bookInfo.title) [$($bookInfo.lifecycle)]"
}

$final = Invoke-JsonApi 'Get' '/api/v1/books'
Write-Host "TOTAL $($final.total)"
