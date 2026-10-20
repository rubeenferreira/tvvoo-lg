"""Gera M3U do TvVoo. Python 3, sem dependencias externas."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request


def get_json(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=45) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def clean(value):
    return str(value or '').replace('\r', ' ').replace('\n', ' ').replace('"', "'")


def media_available(url):
    """Confirma manifesto e inicio de um segmento; nao testa descodificacao."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        for level in range(3):
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=6) as response:
                data = response.read(4096 if level else 131072)
                base = response.url
            if data.startswith(b'#EXTM3U'):
                lines = data.decode('utf-8').splitlines()
                paths = [line.strip() for line in lines if line.strip() and not line.startswith('#')]
                if not paths:
                    return False
                url = urllib.parse.urljoin(base, paths[0])
            else:
                return len(data) >= 188 and (data[0] == 0x47 or b'ftyp' in data[:32] or b'styp' in data[:32])
    except Exception:
        return False
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paises', default='pt', help='Codigos separados por virgulas, ou all')
    parser.add_argument('--servidor', default='https://tvvoo.hayd.uk')
    parser.add_argument('--saida', default=str(Path(__file__).with_name('tvvoo.m3u')))
    args = parser.parse_args()
    base = args.servidor.rstrip('/')
    manifest = get_json(base + '/manifest.json')
    catalogs = {c['id'].removeprefix('vavoo_tv_'): c for c in manifest['catalogs']
                if c['id'].startswith('vavoo_tv_') and not c['id'].startswith('vavoo_tv_home_')}
    countries = list(catalogs) if args.paises == 'all' else args.paises.split(',')
    entries, failures = [], []

    def resolve(meta):
        identifier = urllib.parse.quote(meta['id'], safe='')
        data = get_json(base + '/stream/tv/' + identifier + '.json')
        urls = list(dict.fromkeys(s['url'] for s in data.get('streams', [])
                    if '/live/manifest.m3u8?' in s.get('url', '')))
        if not urls:
            raise ValueError('Sem link com renovacao de sessao')
        checked = [(url, media_available(url)) for url in urls]
        # Mantem fontes indisponiveis como alternativas, mas coloca fontes
        # que entregam dados primeiro. Falhas podem ser transitorias.
        checked.sort(key=lambda item: not item[1])
        return checked

    for country in countries:
        if country not in catalogs:
            raise ValueError('Pais desconhecido: ' + country + '; disponiveis: ' + ','.join(catalogs))
        catalog = catalogs[country]
        data = get_json(base + '/catalog/tv/' + catalog['id'] + '.json')
        metas = data.get('metas', [])
        if not metas:
            raise ValueError('Catalogo vazio: ' + country)
        print(country + ': ' + str(len(metas)) + ' canais', flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(resolve, meta): meta for meta in metas}
            results = {}
            for future in concurrent.futures.as_completed(futures):
                meta = futures[future]
                try:
                    results[meta['id']] = future.result()
                except Exception as exc:
                    failures.append(country + ': ' + meta['name'] + ': ' + str(exc))
            for meta in metas:
                for index, (url, available) in enumerate(results.get(meta['id'], []), 1):
                    name = clean(meta['name']) + (f' (alternativa {index})' if index > 1 else '')
                    logo = clean(meta.get('logo') or meta.get('poster'))
                    group = country.upper() if available else country.upper() + ' - Sem resposta no teste'
                    entries.extend([f'#EXTINF:-1 tvg-logo="{logo}" group-title="{clean(group)}",{name}', url])
    if failures:
        report = Path(args.saida).with_suffix('.erros.txt')
        report.write_text('\n'.join(failures), encoding='utf-8')
        raise RuntimeError(f'{len(failures)} canais falharam. Lista anterior preservada. Ver {report}')
    if not entries:
        raise RuntimeError('Sem canais. Lista anterior preservada.')
    target = Path(args.saida)
    temporary = target.with_suffix('.tmp')
    temporary.write_text('#EXTM3U\n' + '\n'.join(entries) + '\n', encoding='utf-8')
    temporary.replace(target)
    print(f'Criado: {target} ({len(entries)//2} entradas)', flush=True)


if __name__ == '__main__':
    main()


