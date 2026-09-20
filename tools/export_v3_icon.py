"""将本次生成图稿的轮廓导出为实际ICO/PNG/SVG；仅需要Pillow。

图稿轮廓是图像生成输出的简化追踪，不是原占位字母。构建时运行，避免旧图标混包。
不读取/修改用户数据、配置或运行进程；输出固定在仓库assets及web/public内。
"""
from __future__ import annotations
import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]

def export(root: Path=ROOT) -> None:
    assets=root/'assets';spec=json.loads((assets/'v3-icon.paths.json').read_text(encoding='utf-8'))
    theme=json.loads((assets/'ui-theme.json').read_text(encoding='utf-8')) if (assets/'ui-theme.json').exists() else None
    if theme:spec['foreground']=theme['colors']['accent'];spec['background']=theme['colors']['surface']
    if spec.get('schema')!=1 or spec.get('size')!=512:raise ValueError('Unexpected icon data')
    scale=4
    image=Image.new('RGBA',(512*scale,512*scale));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle(tuple(v*scale for v in spec['tile']),radius=spec['radius']*scale,fill=spec['background'])
    for contour in spec['contours']:
        draw.polygon([(x*scale,y*scale) for x,y in contour['points']],fill=spec['background'] if contour['hole'] else spec['foreground'])
    image.resize((512,512),Image.Resampling.LANCZOS).save(assets/'icon.png',optimize=True)
    image.resize((256,256),Image.Resampling.LANCZOS).save(assets/'icon.ico',sizes=[(n,n)for n in (16,20,24,32,40,48,64,128,256)])
    paths=[]
    for contour in spec['contours']:
        p=contour['points'];paths.append('M'+' L'.join(f'{x} {y}'for x,y in p)+' Z')
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
    svg+=f'<rect x="20" y="20" width="472" height="472" rx="96" fill="{spec["background"]}"/>'
    svg+=f'<path d="{" ".join(paths)}" fill="{spec["foreground"]}" fill-rule="evenodd"/></svg>\n'
    (assets/'icon.svg').write_text(svg,encoding='utf-8')
    public=root/'web/public';public.mkdir(parents=True,exist_ok=True)
    image.resize((180,180),Image.Resampling.LANCZOS).save(public/'app-icon.png',optimize=True)

if __name__=='__main__':export()
