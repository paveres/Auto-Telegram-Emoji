__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import gzip, json, io, hashlib, subprocess, zipfile, math, os, sys, secrets, threading
_NATIVE_SLOT = threading.BoundedSemaphore(1)
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from rlottie_python import LottieAnimation
import imageio_ffmpeg
from .vector import transform

class Renderer:

    def __init__(self, root, catalog):
        self.root = Path(root)
        self.catalog = catalog
        self.folder = self.root / 'data'
        self.folder.mkdir(parents=True, exist_ok=True)

    def image(self, raw, size=360, fraction=0.4):
        d = json.loads(gzip.decompress(raw))
        a = LottieAnimation.from_data(json.dumps(d))
        count = int(d['op'] - d.get('ip', 0))
        return a.render_pillow_frame(frame_num=max(0, min(count - 1, int(count * fraction))), width=size, height=size).convert('RGBA')

    def isolated(self, action, **payload):
        jobs = self.folder / 'jobs'
        jobs.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(12)
        request = jobs / (key + '.json')
        response = jobs / (key + '.result')
        request.write_text(json.dumps({'root': str(self.root.resolve()), 'folder': str(self.folder.resolve()), 'action': action, **payload}, ensure_ascii=False), encoding='utf8')
        request.chmod(384)
        payload.clear()
        try:
            with _NATIVE_SLOT:
                import shutil
                if shutil.disk_usage(self.folder).free < 512 * 1024 * 1024:
                    raise RuntimeError('Недостаточно места для безопасной сборки. Сообщите продавцу.')
                env = dict(os.environ, AUTO_EMOJI_RENDER_CHILD='1', AUTO_EMOJI_ROOT=str(self.root.resolve()), PYTHONPATH=str(Path(__file__).resolve().parent.parent) + os.pathsep + os.environ.get('PYTHONPATH', ''), OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
                subprocess.run([sys.executable, '-m', 'auto_telegram_emoji.render_worker', str(request.resolve()), str(response.resolve())], cwd=self.root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=660)
            result = json.loads(response.read_text(encoding='utf8')) if response.exists() else {'error': 'Процесс рендера остановлен по лимиту ресурсов.'}
            if result.get('error'):
                if result.get('validation'):
                    raise ValueError(result['error'])
                raise RuntimeError(result['error'])
            return result
        finally:
            request.unlink(missing_ok=True)
            response.unlink(missing_ok=True)

    def cards(self, raws, path, labels=None, background='black'):
        if not os.environ.get('AUTO_EMOJI_RENDER_CHILD'):
            result = self.isolated('cards', raws=[raw.hex() for raw in raws], path=str(Path(path).resolve()), labels=labels, background=background)
            return [Path(p) for p in result['pages']]
        from . import typography as cards
        paths = []
        per_page = max(16, 4 * math.ceil(len(raws) / 40))
        cell = 280
        gap = 20
        pad = 32
        label_h = 56 if labels else 0
        for start in range(0, len(raws), per_page):
            batch = raws[start:start + per_page]
            cols = min(4, len(batch))
            rows = math.ceil(len(batch) / cols)
            canvas = Image.new('RGB', (pad * 2 + cols * cell + (cols - 1) * gap, pad * 2 + rows * (cell + label_h) + (rows - 1) * gap), background)
            draw = ImageDraw.Draw(canvas)
            for j, raw in enumerate(batch):
                x = pad + j % cols * (cell + gap)
                y = pad + j // cols * (cell + label_h + gap)
                im = self.image(raw, cell)
                canvas.paste(im, (x, y), im)
                draw.rounded_rectangle((x + 10, y + 10, x + 60, y + 60), 25, fill='black')
                draw.text((x + 35, y + 35), str(start + j + 1), font=cards._tfont(30, 700), fill='white', anchor='mm')
                if labels:
                    draw.text((x + cell / 2, y + cell + 28), labels[start + j], font=cards._tfont(21, 700), fill='white' if background == 'black' else 'black', anchor='mm')
                im.close()
            p = Path(str(path) + f'-{start // per_page + 1}.jpg')
            p.parent.mkdir(parents=True, exist_ok=True)
            temp = p.with_suffix('.jpg.tmp')
            canvas.save(temp, format='JPEG', quality=88)
            canvas.close()
            temp.replace(p)
            paths.append(p)
        return paths

    def collections(self):
        from .catalog import NAMES
        p = self.folder / 'cache/v3-collections'
        if Path(str(p) + '-1.jpg').exists():
            return [Path(str(p) + '-1.jpg')]
        return self.cards([self.catalog.get(c, 1).read_bytes() for c in self.catalog.collections()], p, [NAMES[c] for c in self.catalog.collections()])

    def collection(self, c):
        p = self.folder / 'cache' / ('v3-' + c + '-' + str(len(self.catalog.items(c))))
        paths = [Path(str(p) + f'-{i + 1}.jpg') for i in range(math.ceil(len(self.catalog.items(c)) / max(16, 4 * math.ceil(len(self.catalog.items(c)) / 40))))]
        if all((p.exists() for p in paths)):
            return paths
        return self.cards([self.catalog.get(c, n + 1).read_bytes() for n in range(len(self.catalog.items(c)))], p)

    def selected(self, o, personal=False):
        d = o['data']
        raws = []
        for i, (c, n) in enumerate(d['cart'], 1):
            p = self.catalog.get(c, n)
            from .textflow import value
            text = value(d, i)
            style = {**d.get('style_global', {}), **d.get('styles', {}).get(str(i), {})}
            raws.append(transform(p, text, self.catalog.base / 'fonts', d.get('gradient', 0), d.get('color', 0), style) if personal and text else p.read_bytes())
        path = self.folder / 'orders' / o['id'] / str(d['rev'])
        path.mkdir(parents=True, exist_ok=True)
        labels = [self.catalog.label(c, n) for c, n in d['cart']]
        return (raws, self.cards(raws, path / 'preview', labels), path)

    def video(self, raws, path, watermark):
        if len(raws) > 9:
            return self.large_video(raws, path, watermark)
        n = len(raws)
        cols = min(3, n) if n <= 9 else math.ceil(math.sqrt(n))
        rows = (n + cols - 1) // cols
        cell = min(300, max(96, 960 // cols - 20))
        cw = cell + 20
        ch = cell + 40
        w = cols * cw
        h = rows * ch
        anim = []
        for raw in raws:
            d = json.loads(gzip.decompress(raw))
            anim.append((LottieAnimation.from_data(json.dumps(d)), d))
        font = ImageFont.truetype(str(self.root / 'assets/fonts/montserrat.ttf'), 20)
        proc = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}', '-r', '24', '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', '-threads', '1', '-crf', '23', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            for frame in range(72):
                canvas = Image.new('RGB', (w, h), 'black')
                draw = ImageDraw.Draw(canvas)
                for i, (a, d) in enumerate(anim):
                    count = int(d['op'] - d.get('ip', 0))
                    im = a.render_pillow_frame(frame_num=min(count - 1, int(frame / 24 * d['fr']) % count), width=cell, height=cell).convert('RGBA')
                    x = i % cols * cw + 10
                    y = i // cols * ch + 10
                    canvas.paste(im, (x, y), im)
                    draw.text((x + 6, y + 4), str(i + 1), fill='white', font=font, stroke_width=2, stroke_fill='black')
                    draw.text((x + cell / 2, y + cell + 15), watermark, fill=(145, 150, 165), font=font, anchor='mm')
                proc.stdin.write(canvas.tobytes())
        finally:
            proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError('Ошибка сборки видео')

    def large_video(self, raws, path, watermark):
        import mmap, tempfile, gc
        cols = math.ceil(math.sqrt(len(raws)))
        rows = (len(raws) + cols - 1) // cols
        cell = max(80, min(160, 960 // cols - 20))
        cw = cell + 20
        ch = cell + 30
        w = cols * cw
        h = rows * ch
        if w % 2:
            w += 1
        if h % 2:
            h += 1
        stride = w * h * 3
        frames = 48
        font = ImageFont.truetype(str(self.root / 'assets/fonts/montserrat.ttf'), 12)
        with tempfile.TemporaryFile(dir=path.parent) as buf:
            buf.truncate(stride * frames)
            with mmap.mmap(buf.fileno(), stride * frames) as mapped:
                for i, raw in enumerate(raws):
                    d = json.loads(gzip.decompress(raw))
                    a = LottieAnimation.from_data(json.dumps(d))
                    count = int(d['op'] - d.get('ip', 0))
                    x = i % cols * cw
                    y = i // cols * ch
                    for frame in range(frames):
                        im = a.render_pillow_frame(frame_num=min(count - 1, int(frame / 16 * d['fr']) % count), width=cell, height=cell).convert('RGBA')
                        tile = Image.new('RGB', (cw, ch), 'black')
                        tile.paste(im, (10, 5), im)
                        draw = ImageDraw.Draw(tile)
                        draw.text((12, 6), str(i + 1), fill='white', font=font, stroke_width=1, stroke_fill='black')
                        draw.text((cw / 2, ch - 12), watermark, fill=(145, 150, 165), font=font, anchor='mm')
                        rawtile = tile.tobytes()
                        for line in range(ch):
                            offset = frame * stride + ((y + line) * w + x) * 3
                            mapped[offset:offset + cw * 3] = rawtile[line * cw * 3:(line + 1) * cw * 3]
                    del a
                    gc.collect()
                mapped.flush()
                mapped.close()
                buf.seek(0)
                result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-y', '-threads', '1', '-filter_threads', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}', '-r', '16', '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', '-threads', '1', '-crf', '23', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)], stdin=buf, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
                if result.returncode != 0:
                    raise RuntimeError('Ошибка сборки большого предпросмотра: ' + result.stderr.decode(errors='replace')[-500:])

    def build(self, o, final=False):
        if not os.environ.get('AUTO_EMOJI_RENDER_CHILD'):
            result = self.isolated('build', order=o, final=final)
            return ([Path(p) for p in result['pages']], Path(result['video']), Path(result['archive']) if result.get('archive') else None)
        raws, pages, path = self.selected(o, True)
        video = path / 'preview.mp4'
        self.video(raws, video, 'Заказ ' + o['id'])
        archive = None
        if final:
            archive = path / 'emoji.zip'
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
                for i, ((c, n), raw) in enumerate(zip(o['data']['cart'], raws), 1):
                    z.writestr(f'{i:02}_{c}_{n:03}.tgs', raw)
            with zipfile.ZipFile(archive) as z:
                if z.testzip() or len(z.namelist()) != o['qty']:
                    raise RuntimeError('Неверный архив')
        return (pages, video, archive)

    def light_cards(self, o):
        raws, _, path = self.selected(o, True)
        return self.cards(raws, path / 'light', background='white')
