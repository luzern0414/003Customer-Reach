<script setup lang="ts">
import {computed} from 'vue'
const props=defineProps<{analysis:any}>()
const fitLabels:Record<string,string>={related:'方向相关',gap:'能力缺口',unknown:'待核验'}
const status=computed(()=>props.analysis?.stale?'资料已变化，需重新分析':props.analysis?.status==='completed'?'已完成引用核验':props.analysis?.status==='partial'?'部分分析通过引用核验':'分析尚未完成')
</script>
<template>
  <div class="lead-analysis">
    <div v-if="!analysis" class="acquisition-empty"><h3>先核验需求，再判断适配</h3><p>AI 会结合已保存的产品画像与本客户来源资料，逐项列出匹配依据、待核条件和下一步。</p></div>
    <template v-else>
      <p class="analysis-state">{{status}} · {{analysis.created_at}}</p><p class="acquisition-muted">以下是 AI 条件分析。原文引用经程序核验，产品能力来自用户资料；最终资格和技术适配仍需人工确认。</p>
      <p v-if="analysis.reused" class="acquisition-muted">产品与证据未变，复用 {{analysis.analysis_as_of}} 的分析。</p>
      <div v-if="analysis.matches?.length" class="analysis-matrix" role="list" aria-label="需求与产品匹配">
        <article v-for="(match,index) in analysis.matches" :key="index" class="analysis-match" role="listitem">
          <div class="analysis-product"><span>{{fitLabels[match.fit]}}</span><h3>{{match.product.name}}</h3><p v-if="match.product.specifications">{{match.product.specifications}}</p></div>
          <div class="analysis-evidence"><strong>需求依据</strong><blockquote>{{match.quote}}</blockquote><a :href="match.evidence.url" target="_blank" rel="noopener noreferrer">原始来源 ↗</a></div>
          <div class="analysis-reason"><strong>匹配判断与待核条件</strong><p>{{match.reason}}</p><strong>下一步</strong><p>{{match.next_step}}</p></div>
        </article>
      </div>
      <p v-else class="acquisition-muted">当前尚无通过引用核验的具体匹配项。</p>
      <div v-if="analysis.questions?.length" class="analysis-questions"><h3>需要确认的问题</h3><ul><li v-for="question in analysis.questions" :key="question">{{question}}</li></ul></div>
      <details v-if="analysis.limitations?.length||analysis.coverage?.omitted_evidence" class="acquisition-disclosure"><summary>分析范围与资料缺口</summary><p v-if="analysis.coverage">纳入 {{analysis.coverage.selected_evidence}} / {{analysis.coverage.total_evidence}} 个证据片段，{{analysis.coverage.selected_projects}} / {{analysis.coverage.total_projects}} 条公告。</p><p v-for="limitation in analysis.limitations" :key="limitation">{{limitation}}</p></details>
    </template>
  </div>
</template>
