<script setup lang="ts">
import { computed } from 'vue'
import { parseShellState } from '../../src/shell-state'

const route = useRoute()
const state = computed(() => parseShellState(route.query.state))
</script>

<template>
  <div class="reader-shell">
    <header class="reader-header">
      <NuxtLink class="reader-brand" to="/">墨页 <span>MindBook</span></NuxtLink>
      <nav class="reader-nav" aria-label="读者导航">
        <NuxtLink class="active" to="/">首页</NuxtLink>
        <a href="#library">书库</a>
        <a href="#ranking">排行榜</a>
        <a href="#finished">完本</a>
        <a href="#free">免费</a>
      </nav>
      <div class="reader-actions">
        <form class="search-box" action="/" method="get">
          <input name="q" aria-label="搜索作品" placeholder="搜索书名或作者" />
          <button type="submit">搜索</button>
        </form>
        <a class="login-link" href="?state=unauthorized">登录</a>
      </div>
    </header>

    <main v-if="state === 'ready'" class="reader-main">
      <section class="reader-hero" aria-labelledby="hero-title">
        <div>
          <p class="eyebrow">今日精选 · 读一本好故事</p>
          <h1 id="hero-title">在故事里，找到下一页。</h1>
          <p class="hero-copy">从连载、完本和免费作品中，继续你的阅读。</p>
          <div class="hero-actions"><a class="primary-button" href="#library">进入书库</a><a class="quiet-button" href="#free">看看免费作品</a></div>
        </div>
        <div class="hero-note" aria-label="阅读提示"><span>本周热读</span><strong>《长夜微光》</strong><small>第 42 章 · 玄幻连载</small></div>
      </section>

      <section class="reader-section" aria-labelledby="continue-title">
        <div class="section-heading"><div><p class="eyebrow">只为你保留</p><h2 id="continue-title">继续阅读</h2></div><a href="?state=unauthorized">登录同步书架 →</a></div>
        <article class="continue-row"><div class="book-mark mark-coral">长夜<br />微光</div><div class="continue-info"><h3>《长夜微光》</h3><p>第 41 章 · 灯火照见旧山河</p><div class="progress"><span /></div></div><a class="text-button" href="#read">继续阅读</a></article>
      </section>

      <section id="library" class="reader-section" aria-labelledby="featured-title">
        <div class="section-heading"><div><p class="eyebrow">编辑精选</p><h2 id="featured-title">今天读什么</h2></div><a href="#library">查看全部 →</a></div>
        <div class="book-grid"><article class="book-card"><div class="book-mark mark-teal">潮生<br />旧梦</div><div><h3>《潮生旧梦》</h3><p>南枝 · 古言</p><span class="tag">连载中</span></div></article><article class="book-card"><div class="book-mark mark-gold">远山<br />来信</div><div><h3>《远山来信》</h3><p>林渡 · 现实题材</p><span class="tag">完本</span></div></article><article class="book-card"><div class="book-mark mark-blue">星河<br />回响</div><div><h3>《星河回响》</h3><p>闻舟 · 科幻</p><span class="tag">免费</span></div></article></div>
      </section>

      <section id="ranking" class="reader-section ranking-section" aria-labelledby="ranking-title">
        <div class="section-heading"><div><p class="eyebrow">实时榜单</p><h2 id="ranking-title">热读上升</h2></div><a href="#ranking">完整榜单 →</a></div>
        <ol class="ranking-list"><li><b>01</b><span>《人间借火》</span><small>都市 · 更新至 96 章</small></li><li><b>02</b><span>《潮生旧梦》</span><small>古言 · 更新至 71 章</small></li><li><b>03</b><span>《星河回响》</span><small>科幻 · 更新至 38 章</small></li></ol>
      </section>
    </main>

    <main v-else class="reader-state" :data-state="state" aria-live="polite">
      <div v-if="state === 'loading'" class="state-card"><div class="spinner" /><h1>正在打开书库</h1><p>作品内容马上就到。</p></div>
      <div v-else-if="state === 'empty'" class="state-card"><div class="state-symbol">○</div><h1>这里还没有作品</h1><p>换个筛选条件，再试试看。</p><a class="primary-button" href="?state=ready">回到首页</a></div>
      <div v-else-if="state === 'error'" class="state-card"><div class="state-symbol">!</div><h1>书库暂时没有响应</h1><p>请稍后重试，阅读进度不会丢失。</p><a class="primary-button" href="?state=ready">重新加载</a></div>
      <div v-else class="state-card"><div class="state-symbol">↗</div><h1>登录后继续阅读</h1><p>登录即可同步书架、进度和互动记录。</p><a class="primary-button" href="?state=ready">返回游客首页</a></div>
    </main>

    <footer class="reader-footer"><span>墨页 MindBook</span><span>内容 · 社区 · 阅读</span></footer>
  </div>
</template>
