import json
import subprocess
import unittest
import app

HARNESS = r'''
const vm=require('vm'), assert=require('assert');
function node(){return {style:{},children:[],textContent:'',_html:'',set innerHTML(v){this._html=v;this.children=[]},get innerHTML(){return this._html},appendChild(c){this.children.push(c)},addEventListener(k,f){this[k]=f},querySelectorAll(){return []}}}
const els={}; const ctx={URL, document:{getElementById:id=>els[id] ||= node(),createElement:()=>node()},fetch:async()=>({json:async()=>ctx.response})};
vm.createContext(ctx);vm.runInContext(SCRIPT,ctx);vm.runInContext('run = p => { globalThis.chosen = selectedCategory; }; lastQ="test"',ctx);
(async()=>{
ctx.response={categories:[{slug:'a',title:'A',count:3},{slug:'b',title:'B',count:2}],selected_category:null};
await vm.runInContext('beginSearch()',ctx);
assert.equal(ctx.chosen,undefined);
els.categories.children[2].click();assert.equal(ctx.chosen,'b');
ctx.response={categories:[{slug:'a',title:'A',count:5}],selected_category:{slug:'a',title:'A',count:5}};
await vm.runInContext('beginSearch()',ctx);assert.equal(ctx.chosen,'a');
els.categories.children[2].click();assert.equal(ctx.chosen,'');
console.log('Category UI auto, choice, fallback: PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
'''

class CategoryUITests(unittest.TestCase):
    def test_auto_choice_and_fallback(self):
        script=app.PAGE.split('<script>')[1].split('</script>')[0]
        subprocess.run(['node','-e',HARNESS.replace('SCRIPT',json.dumps(script))],check=True,capture_output=True)
