/** 验证流式排版开头不会闪露，同时保留完整Markdown与合法代码。 */
import {test} from 'node:test'
import {strict as assert} from 'node:assert'
import {displayMarkdown,configureMarkdown} from '../src/markdown.ts'
import {getMarkdown,parseMarkdownToStructure} from 'stream-markdown-parser'

test('only unfinished formatting prefixes are hidden',()=>{
  assert.equal(displayMarkdown('1. **已完成**\n2. **',false),'1. **已完成**\n2. ')
  assert.equal(displayMarkdown('1. ***',false),'1. ')
  assert.equal(displayMarkdown('**完整粗体**',false),'**完整粗体**')
  assert.equal(displayMarkdown('***完整强调***',false),'***完整强调***')
  assert.equal(displayMarkdown('***',false),'***')
})

test('CJK punctuation emphasis renders through the actual renderer AST',()=>{
  const base=getMarkdown('cjk-regression'),md=configureMarkdown(base)
  assert.equal(configureMarkdown(base),md)
  const nodes:any[]=parseMarkdownToStructure('**轨道灯和筒灯的采购均未确认。**现有资料未提及',md,{final:true})
  assert.equal(nodes[0].children[0].type,'strong')
  assert.equal(nodes[0].children[0].children[0].content,'轨道灯和筒灯的采购均未确认。')
  assert.equal(nodes[0].children[1].content,'现有资料未提及')
})

test('CJK plugin preserves code, escapes, tables and raw HTML policy',()=>{
  const md=configureMarkdown(getMarkdown('markdown-controls'))
  const html=md.render('`**代码。**保留`\n\n\\*\\*字面量\\*\\*\n\n| 名称 | 数量 |\n| --- | --- |\n| 轨道灯 | 20 |\n\n<script>alert(1)</script>')
  assert.ok(html.includes('<code>**代码。**保留</code>'))
  assert.ok(html.includes('**字面量**'))
  assert.ok(html.includes('<table>'))
  assert.ok(!html.includes('<script>')&&html.includes('&lt;script&gt;'))
  assert.ok(!md.render('[不安全](javascript:alert(1))').includes('href="javascript:'))
})
test('completed text, code and escaped literals remain intact',()=>{
  for(const value of ['**','```python\nx = "**','`a**','`a**`\n**完成**','\\*\\*','乘法 2 * 3']){
    assert.equal(displayMarkdown(value,true),value)
  }
  assert.equal(displayMarkdown('```python\nx = "**',false),'```python\nx = "**')
  assert.equal(displayMarkdown('`a**',false),'`a**')
  assert.equal(displayMarkdown('`a**`\n**完成**',false),'`a**`\n**完成**')
})
