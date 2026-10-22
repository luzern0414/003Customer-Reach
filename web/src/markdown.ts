import cjkFriendly from 'markdown-it-cjk-friendly'
import MarkdownIt from 'markdown-it'

const configured=new WeakMap<object,ReturnType<typeof MarkdownIt>>()
/** md为渲染器提供的实例；返回官方markdown-it+CJK插件解析器，不改写原文，HTML始终关闭。 */
export function configureMarkdown(md:any):any{let parser=configured.get(md);if(!parser){parser=new MarkdownIt({html:false,linkify:true}).use(cjkFriendly);configured.set(md,parser)}return parser}

/** content为真实Markdown原文，final表示已终结；仅隐藏流式末尾未完成的粗体开头。
 * 完整回答不改写，代码围栏/行内代码/转义星号保留；避免模型单独吐出**时闪出裸标记。
 */
export function displayMarkdown(content:string,final:boolean):string {
  if(final)return content
  const ending=content.match(/(?<![\\*])(\*{2,3})([ \t]*)$/)
  if(!ending)return content
  let fence='',plain=''
  for(const line of content.split('\n')){
    const marker=line.match(/^ {0,3}(`{3,}|~{3,})/)
    if(marker){if(!fence)fence=marker[1];else if(marker[1][0]===fence[0]&&marker[1].length>=fence.length)fence='';continue}
    if(!fence)plain+='\n'+line
  }
  if(fence)return content
  // 完整行内代码不参与标记计数；未闭合的行内代码也不作排版标记处理。
  plain=plain.replace(/(?<!\\)(`+)([^`]*?)\1/g,'')
  if((plain.match(/(?<!\\)`/g)||[]).length%2)return content
  if(/^ {0,3}\*{3}\s*$/.test(content.split('\n').at(-1)||''))return content
  const marker=ending[1]
  const count=(plain.match(/(?<![\\*])\*{2,3}(?!\*)/g)||[]).filter(x=>x===marker).length
  return count%2?content.slice(0,content.length-ending[0].length):content
}
