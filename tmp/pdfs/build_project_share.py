"""Build the project-sharing PDF from the retained experiment snapshot."""
from pathlib import Path
import csv
import json
import statistics
from xml.sax.saxutils import escape

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                               TableStyle, PageBreak, KeepTogether)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/pdf/HGTSA_项目分享与实验结果解读.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont('CN', 'C:/Windows/Fonts/simhei.ttf'))
pdfmetrics.registerFont(TTFont('Latin', 'C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('Mono', 'C:/Windows/Fonts/consola.ttf'))

def load_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

paper = load_csv(ROOT / 'results/paper/experiment_table.csv')
smoke = load_csv(ROOT / 'results/smoke/summary.csv')
raw = load_csv(ROOT / 'results/paper/raw_runs.csv')
paper_manifest = json.loads((ROOT / 'results/paper/manifest.json').read_text(encoding='utf-8'))
smoke_manifest = json.loads((ROOT / 'results/smoke/manifest.json').read_text(encoding='utf-8'))
paper_runs = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT / 'results/paper/runs').glob('*.json'))]
smoke_runs = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT / 'results/smoke/runs').glob('*.json'))]
assert len(paper_runs) == 40 and len(smoke_runs) == 10
assert len(paper) == 5 and len(smoke) == 10
assert smoke_manifest['signature']['config']['time_limit'] == 60
errors = {r['Instance']: 100*(float(r['Best'])-float(r['LB']))/float(r['LB']) for r in smoke}
mre = statistics.mean(errors.values())

W, H = A4
M = 43
CW = W - 2*M
NAVY = colors.HexColor('#20364b')
BLUE = colors.HexColor('#2b648a')
MUTED = colors.HexColor('#5c6977')
LIGHT = colors.HexColor('#edf3f7')
BORDER = colors.HexColor('#d4dde5')

styles = {
    'body': ParagraphStyle('body', fontName='CN', fontSize=10, leading=16, spaceAfter=8, wordWrap='CJK'),
    'small': ParagraphStyle('small', fontName='CN', fontSize=8.6, leading=13.2, spaceAfter=6, wordWrap='CJK', textColor=MUTED),
    'h1': ParagraphStyle('h1', fontName='CN', fontSize=23, leading=30, spaceAfter=14),
    'h2': ParagraphStyle('h2', fontName='CN', fontSize=13, leading=19, spaceBefore=9, spaceAfter=8),
    'cell': ParagraphStyle('cell', fontName='CN', fontSize=8.7, leading=13, wordWrap='CJK'),
    'cell_center': ParagraphStyle('cellc', fontName='CN', fontSize=8.7, leading=13, alignment=TA_CENTER, wordWrap='CJK'),
    'code': ParagraphStyle('code', fontName='Mono', fontSize=8.1, leading=12, spaceAfter=0),
    'tag': ParagraphStyle('tag', fontName='CN', fontSize=9, leading=13, textColor=BLUE, spaceAfter=8),
}
story=[]

def p(text, kind='body'):
    story.append(Paragraph(text, styles[kind]))

def heading(text):
    p(text, 'h2')

def page(number, title, summary):
    if story:
        story.append(PageBreak())
    p(f'项目分享说明  /  {number:02d}', 'tag')
    p(title, 'h1')
    p(summary)

def table(headers, rows, widths, center_cols=()):
    data = [[Paragraph(escape(str(x)), styles['cell_center']) for x in headers]]
    for row in rows:
        data.append([Paragraph(escape(str(x)), styles['cell_center'] if i in center_cols else styles['cell'])
                     for i,x in enumerate(row)])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0), LIGHT),
        ('GRID',(0,0),(-1,-1),0.5,BORDER),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f8fafc')]),
    ]))
    story.append(t)
    story.append(Spacer(1,9))

def callout(text):
    t=Table([[Paragraph(text,styles['body'])]], colWidths=[CW])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('BOX',(0,0),(-1,-1),0.6,BORDER),
                          ('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),11),
                          ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(t)
    story.append(Spacer(1,9))

def code(text):
    parts = [Paragraph(escape(line).replace(' ', '&#160;'), styles['code']) for line in text.splitlines()]
    t=Table([[parts]], colWidths=[CW])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f4f6f8')),
                          ('BOX',(0,0),(-1,-1),0.5,BORDER),
                          ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
                          ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story.append(t)
    story.append(Spacer(1,8))


page(1, 'HGTSA 项目分享与实验结果解读',
     '本说明面向共同开展论文复现、准备汇报和接手运行项目的同伴。内容依据项目 README、两份展示表及其原始运行记录整理，数据快照日期为 2026 年 10 月 20 日。')
callout('当前结论：正式参数实验已完成 MK01 至 MK04，各 10 次，共 40 次，全部达到对应下界；十个算例的完整 100 次实验尚未完成。smoke 是另一批单次限时流程测试，不能与正式实验混合统计。')
heading('项目要解决的问题')
p('采用 Python 实现混合遗传禁忌搜索算法 HGTSA，求解柔性作业车间调度问题 FJSP。每道工序可以选择加工机器，同时需要安排各机器上的加工顺序，目标是最小化 Makespan，即所有工件完成加工的总工期。实验仅使用项目已有的 Brandimarte MK01 至 MK10 数据。')
heading('算法主流程')
p('初始化可行种群 → 轮盘赌选择 → 路径重连交叉 → 关键路径变异 → 候选解小规模 TS → 生成子代 → 子代大规模 TS → 父子合并择优。TS 合并 N8 同机移动与 k-insertion 跨机插入邻域。')
heading('两批实验的设置')
table(['项目','paper 正式参数实验','smoke 流程测试'],[
    ['当前完成范围','MK01 至 MK04，各 10 次','MK01 至 MK10，各 1 次'],
    ['PS / Pc / Pm','30 / 0.9 / 0.1','4 / 0.9 / 0.1'],
    ['smallIter / largeIter','1200 / 15000','5 / 12'],
    ['最大 GA 代数','100','2'],
    ['单次时间上限','无时间上限','60 秒'],
    ['主要用途','阶段性解质量与重复表现评价','流程验证及限时结果观察'],
], [103,202, CW-305])
p('smallIter 与 largeIter 是连续未改进步数上限，不是固定总迭代次数；发现改善后计数重置。达到 LB 可以提前停止。最大 GA 代数 100 是本项目的设置，论文未明确给出该值。', 'small')

page(2, '正式参数实验表如何解读',
     '材料：results/paper/experiment_table.csv。表格只覆盖已经完成的四个算例，不包含尚未获得正式结果的 MK05 至 MK10。所有数值均为 Makespan 或其相对误差，未包含计算耗时。')
formal_rows=[]
for r in paper:
    formal_rows.append([r[k] for k in ['Instance','UB（本机）','UB（原paper）','LB','Best','Mav','b-MRE (%)','av-MRE (%)']])
table(['算例','本机 UB','论文 UB','LB','Best','Mav','b-MRE %','av-MRE %'],
      formal_rows,[60,65,65,42,48,60, CW-440,100] if False else [59,62,62,43,48,62,86, CW-422],center_cols=range(8))
heading('为什么选择这八列')
table(['列项','解释与选择理由'],[
    ['Instance','标识测试算例，使结果可以回溯到同一份基准数据。'],
    ['UB（本机）','本批找到的最好可行调度值，给出该最小化问题的上界。'],
    ['UB（原paper）','论文采用的历史已知上界，作为对照目标；不是当前最新纪录声明。'],
    ['LB','论文采用的下界，判断解的差距；可行解达到有效 LB 时即达到最优。'],
    ['Best','该算例十次独立运行中的最小值，衡量本批的最好求解能力。'],
    ['Mav','十次 Makespan 的算术平均，反映本批重复运行的平均表现。'],
    ['b-MRE / av-MRE','分别汇总各算例 Best / Mav 相对 LB 的百分比误差，便于跨算例对照。'],
], [103,CW-103])
heading('为什么这些数值相等')
p('原始记录中，四个算例的 40 次运行均以达到下界结束。因此每例均有 Best = Mav = LB，本机 UB 又按最好可行值定义，所以与 Best 重复。论文 UB 在这四例也恰好等于 LB，最终各列数值相同。')
p('本机 UB 与 Best 保留两列，是为了同时对应“可行解上界”和论文常用的“最好运行结果”术语，不代表两份独立证据。Overall 行的两项 MRE 均为 0.00%，不是四舍五入所致。其余单元格的横线表示该位置不适用。', 'small')
callout('可支持的结论：在 MK01 至 MK04 上，各十次独立运行均达到下界，该四例子集的 b-MRE 和 av-MRE 为 0%。不能据此声称完整十例实验完成，或总体性能优于论文。')

page(3, '单次限时测试表如何解读',
     '材料：results/smoke/summary.csv。每个算例仅独立运行一次，使用简化参数，单次最多 60 秒。CSV 有五列；下表额外增加 RE，便于解读，RE 不是原 CSV 的列项。')
smoke_rows=[[r['Instance'],r['UB'],r['LB'],r['Best'],r['Mav'],f"{errors[r['Instance']]:.2f}"] for r in smoke]
table(['算例','实测 UB','LB','Best','Mav','RE %（本说明计算）'],smoke_rows,
      [65,72,65,65,65,CW-332],center_cols=range(6))
heading('为什么 UB、Best 和 Mav 完全相同')
p('单次运行只得到一个观测值 C，该值既是可行调度给出的上界，也是这一次的最好值，其算术平均仍为 C。因此 UB = Best = Mav 是样本量为 1 的必然结果，不能用来证明算法稳定。这里的 UB 也不是论文中的最优已知 UB。')
heading('为什么没有达到论文数值')
p('smoke 的种群只有 4 个，smallIter 与 largeIter 仅为 5 和 12，最大 GA 代数为 2，还设置了 60 秒上限。这些因素共同限制了探索范围和局部搜索深度。记录显示 MK01 约在 36.17 秒达到 LB=40，其余九例均因达到时间上限停止；表中数值是这些条件下结束时找到的结果。')
heading('两张表为什么选择不同的列')
p('正式表着重回答“能否达到论文目标、重复运行平均表现如何”，因此提供论文 UB、Mav 和总体 MRE。smoke 表着重回答“是否得到可行结果、距离下界有多远”，因而保留逐例 UB、LB 和 Best，未单列论文 UB 与总体 MRE。当前 CSV 保留的 Mav 只是单次值的重复表达，不增加平均性能证据。')
p('展示层需区分：smoke 的网页仍是 Instance、UB、LB、Best 四列精简版；CSV 则有包含 Mav 的五列。两者数据来源相同，README 已按实际列项说明；实验说明.txt 中“四列表格”的旧表述应以当前 CSV 和 README 为准。', 'small')

page(4, 'MRE 可以算 但结论要有限定',
     'MRE 的作用是把不同量级的 Makespan 转成相对下界的百分比差距，再按算例等权平均。它不是算法耗时、成功率，也不是“距离真实最优值”的精确误差；对于未证明最优的算例，下界可能仍低于真实最优值。')
heading('计算方法')
code('Best RE = 100 * (Best - LB) / LB\nMean RE = 100 * (Mav  - LB) / LB\nb-MRE   = mean(Best RE across included instances)\nav-MRE  = mean(Mean RE across included instances)')
p('例如 smoke 的 MK02：Best=32，LB=26，因此 RE=100×(32-26)/26≈23.08%。各算例权重相同，不能直接用不同算例的 Makespan 相加后除以 LB 之和来替代此处的 MRE。')
heading('如果把 smoke 的总体 MRE 放入表格')
callout(f'当前 smoke 的 b-MRE = av-MRE ≈ {mre:.2f}%。这表示十个算例在本批简化参数、各一次、单次最多 60 秒的设置下，相对各自 LB 的误差等权平均约为 {mre:.2f}%。该数字可以作为这批观测的描述。')
p('两项数值相等并非稳定性证据。每例只观测一次，Best=Mav，因而两种 MRE 必然相等。十个不同问题各跑一次，不能替代同一个问题跑十次；本批无法揭示同一算例在不同随机种子下的波动，也不能说明十次运行的平均表现。')
heading('为什么不作为流程表的核心结论')
p('第一，若直接并列论文的 b-MRE≈0.21%、av-MRE≈0.29%，容易忽略种群规模、搜索深度、预算和重复次数不同，把实验条件差异全部归因于算法性能。第二，paper 目前只有四例子集，其 0% 也不能直接与 smoke 十例的 36.42% 比较。')
p('第三，总体平均隐藏个例差异：smoke 的 MK01 为 0%，MK10 约为 117.99%。因此流程测试优先展示各算例的结果和 LB，便于识别哪些算例已达下界、哪些仍有较大差距。')
p('省略 MRE 是展示重点的选择，不是公式无效，也不是为了回避结果差距。若在汇报中展示 36.42%，须同时标注“smoke 简化参数、十例各一次、单次最多 60 秒”，并保留逐例数据。', 'small')
heading('为什么论文总体 MRE 不是零')
p('论文十例中，前九例达到下界；MK10 的 LB=189，Best=193，Mav=194.5。该例贡献的误差再除以十个算例，得到 b-MRE≈0.21%、av-MRE≈0.29%。当前 paper 缺少后六例，不能套用论文总体指标。')

page(5, '图表 效率与复现边界',
     '两份展示表主要支持解质量讨论。调度的时间单位与程序运行秒数是两个不同量：Makespan 表示生产方案的总工期，seconds 表示电脑求解该方案消耗的墙钟时间。')
heading('当前图表如何看')
p('paper 的 comparison 图：灰柱是 LB，蓝柱是 Best，绿柱是 Mav；越接近 LB，解质量越好。当前展示版已删除耗时折线和右侧时间轴。甘特图：每行是一台机器，色块是一道工序，J2.3 表示工件 2 的第 3 道工序；窄色块用外置标签和引线。当前版所有工序统一细边框，不用粗边框标记关键路径。')
p('smoke 当前仅保留表格和实验说明，不包含 comparison 图与甘特图。format_results.py 生成当前展示版式；plot_results.py 是基础版式，可能重新出现耗时轴和关键路径粗边框。', 'small')
heading('解质量相同不等于运行效率相同')
time_rows=[]
paper_times={'MK01':0.07,'MK02':0.55,'MK03':0.36,'MK04':0.41}
for name in paper_times:
    rr=[r for r in paper_runs if r['instance']==name]
    time_rows.append([name, f"{statistics.mean(r['seconds'] for r in rr):.2f}",f"{paper_times[name]:.2f}"])
table(['算例','本机平均耗时 / 秒','论文平均耗时 / 秒'],time_rows,[100,205,CW-305],center_cols=range(3))
p('这些时间属于已保存的实验版本。Python 与 Java、硬件、修复方法、邻域生成和评价方式不同，均可能影响效率。当前四例虽然解质量一致，但运行耗时明显更长，不能据此声称效率复现成功；后续修改代码后的性能也不能套用此表。')
heading('向同伴说明的方法差异')
table(['部分','本项目的选择或限制'],[
    ['工序编码','使用唯一工序 ID 消除重复工件编号歧义，另输出工件编号视图。'],
    ['不可行解修复','使用优先级拓扑修复；未核实 Ren-Wang 2012 正文，不能称为逐步等价实现。'],
    ['邻域与评价','实现 N8 块内/块外移动、跨机插入；用图可达性窗口保证无环，未完整复刻全部公式剪枝和快速评价。'],
    ['参数细节','部分距离和禁忌长度使用向上取整；最大 GA 代数默认 100 为项目选择。'],
    ['版本与结论','当前代码新增轻量精确评价；现有 paper 记录对应较早版本，应与其 manifest 一同保存。'],
], [90,CW-90])

page(6, '同伴如何运行与复核',
     'Python 3.10 或以上即可运行，核心求解、CSV 与 SVG 输出仅使用标准库。分享时建议提供整个项目文件夹，保留原始数据、代码、README 和每批实验的运行记录，而不只发送两张汇总表。')
heading('启动与续跑')
p('profile 表示预设参数模式：paper 使用论文五项核心参数；smoke 使用缩减参数。单独指定的命令行参数覆盖对应默认值。smoke 默认时间上限仍为 3 秒，现有批次的 60 秒来自 --time-limit 60。')
p('在项目根目录启动一批新的完整实验，输出目录应不存在或为空：', 'small')
code('python run_experiments.py --profile paper --runs 10 --output results/paper_new')
p('中断后，在同一项目目录执行原命令并添加 --resume：', 'small')
code('python run_experiments.py --profile paper --runs 10 --output results/paper_new --resume')
p('续跑会跳过已经保存的独立运行；正在计算但尚未保存的那一次需要重算。先按 Ctrl+C 等待程序退出，再关闭编辑器。参数、种子、数据和代码指纹需一致，实验期间注意电源和电脑睡眠设置。')
callout('当前现有 paper 批次需特别注意：README 记录其代码指纹已与当前代码不一致，直接 --resume 会拒绝续跑。应恢复原版本，或另建目录开始新批次；不要手改 manifest 指纹强行混合。已有 40 次记录仍可独立分析。')
heading('分享前保留的材料')
table(['文件','同伴用它核查什么'],[
    ['README.md','实验目的、设置、运行方法和方法差异。'],
    ['两份展示 CSV','paper 阶段性对照、smoke 单次限时结果及列项含义。'],
    ['manifest.json 与 runs/','每批真实参数、指纹、种子、停止原因、调度与单次结果。'],
    ['raw_runs.csv / summary.json','独立记录、样本数、统计范围和 MRE 计算依据。'],
], [155,CW-155])
heading('汇报时可以这样表述')
p('“我们使用 Python 复现 HGTSA 的主要框架。在 MK01 至 MK04 四个算例上各完成十次独立运行，全部达到下界，该子集两项 MRE 均为 0%；运行效率尚未与论文一致。另完成了十例各一次、单次最多 60 秒的 smoke 流程测试，其 MRE 约为 36.42%，仅描述这批限时结果。完整十例各十次实验尚未完成，实现也存在已披露的方法差异。”')
p('资料依据：项目 README；results/paper/experiment_table.csv、raw_runs.csv、runs/ 和 manifest.json；results/smoke/summary.csv、summary.json、runs/ 和 manifest.json。论文参照为项目保留论文的表 5、表 6。所有结果以 2026-10-20 的文件快照为准。', 'small')

def footer(c, doc):
    c.saveState()
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(M,34,W-M,34)
    c.setFont('CN',8)
    c.setFillColor(MUTED)
    c.drawString(M,21,'HGTSA 项目分享说明  |  数据快照 2026-10-20')
    c.drawRightString(W-M,21,str(doc.page))
    c.restoreState()

doc=SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=M,leftMargin=M,
                      topMargin=34,bottomMargin=47,title='HGTSA 项目分享与实验结果解读',
                      author='HGTSA 项目组',subject='实验表解读、MRE 适用范围与复现操作说明')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
