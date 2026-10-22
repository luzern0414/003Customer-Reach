<script setup lang="ts">
import {ElMessage} from 'element-plus'
import {CopyDocument} from '@element-plus/icons-vue'
/** fact为真实字段，可空；phone/email/website控制对应动作，wechat仅复制后端判定可用的原值，争议/失效保留文本。 */
const props=defineProps<{fact?:any,phone?:boolean,email?:boolean,website?:boolean,wechat?:boolean}>()
function status(fact:any){return fact?.verification==='disputed'?'争议':fact?.verification==='inactive'?'失效':fact?.verification?.startsWith('人工')?'人工录入':''}
/** fact来自真实字段；只有完整、未失效入口生成链接，短号码不补区号，不接受任意URL协议。 */
function contactLink(){const fact=props.fact,value=fact?.value||'';if(!value||['disputed','inactive'].includes(fact.verification))return ''
  if(props.wechat)return ''
  if(props.phone)return typeof fact.contact_href==='string'&&fact.contact_href.startsWith('tel:')?fact.contact_href:''
  if(props.email)return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)?'mailto:'+value:''
  if(props.website){try{const url=new URL(/^https?:\/\//.test(value)?value:'https://'+value);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password?url.href:''}catch{return ''}}
  return ''
}
/** 无参数；只复制可用微信原值，剪贴板拒绝提示手动选择；不转电话或发起联系请求。 */
async function copyWechat(){if(!props.wechat||props.fact?.copyable!==true||['disputed','inactive'].includes(props.fact.verification))return;const value=props.fact.value;try{await navigator.clipboard.writeText(value);ElMessage.success('已复制')}catch{ElMessage.warning('无法复制，请选择文本复制')}}
</script>
<template>
  <div class="fact-value"><a v-if="contactLink()" :href="contactLink()" :target="website?'_blank':undefined" rel="noopener noreferrer">{{fact.value}}</a><span v-else>{{wechat?'微信 · ':''}}{{fact?.value||'—'}}</span><el-button v-if="wechat&&fact?.copyable===true&&!['disputed','inactive'].includes(fact.verification)" text :icon="CopyDocument" title="复制微信" aria-label="复制微信" @click.stop="copyWechat"/><small v-if="status(fact)" class="fact-state">{{status(fact)}}</small><small v-if="fact?.effective_date||fact?.scope">{{fact.effective_date}} {{fact.scope}}</small><details v-if="fact?.alternatives?.length" class="fact-alternatives"><summary>{{fact.alternatives.length}} 个{{phone?'其他号码':'其他值'}}</summary><p v-for="(item,index) in fact.alternatives" :key="index"><a v-if="phone&&item.contact_href&&!['disputed','inactive'].includes(fact.verification)" :href="item.contact_href">{{item.value}}</a><span v-else>{{item.value}}</span><small>{{item.effective_date}} {{item.scope}}</small></p></details></div>
</template>
