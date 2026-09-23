import json
import subprocess
import unittest
import app

HARNESS = '\nconst vm = require(\'vm\'), assert = require(\'assert\');\nconst elements = {};\nconst ctx = {URL, document: {getElementById: id => elements[id] ||= {style: {}, addEventListener() {}, querySelectorAll() {return []}}}};\nvm.createContext(ctx);vm.runInContext(SCRIPT,ctx);\nctx.attack=\'<img src=x onerror="alert(1)">\';\nctx.p={title:ctx.attack,url:\'javascript:alert(1)\',image:\'data:text/html,<script>alert(1)</script>\',price_toman:ctx.attack,unit_price_toman:2,unit_label:ctx.attack};\nconst html=vm.runInContext(\'cardHtml(p)\',ctx);\nassert(!html.includes(ctx.attack));assert(!html.includes(\'javascript:\'));assert(!html.includes(\'data:text/html\'));\nassert(html.includes(\'&lt;img\'));\nvm.runInContext(\'renderFacets([{group:attack,options:[{label:attack,count:2}]}])\',ctx);\nassert(!elements.facets.innerHTML.includes(ctx.attack));\nvm.runInContext(\'active=[{group:attack,value:attack}];renderActiveBar()\',ctx);\nassert(!elements.fbar.innerHTML.includes(ctx.attack));\nassert.equal(vm.runInContext(\'safeUrl("https://example.com/a?x=1&y=2")\',ctx),\'https://example.com/a?x=1&amp;y=2\');\nconsole.log(\'HTML escaping, numeric fields, facet attributes, active filters and URL protocols: PASS\');\n'

class BrowserSecurityTests(unittest.TestCase):
    def test_rendering(self):
        script = app.PAGE.split("<script>")[1].split("</script>")[0]
        subprocess.run(["node", "-e", HARNESS.replace("SCRIPT", json.dumps(script))], check=True, capture_output=True)
