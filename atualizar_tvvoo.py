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


import re
import unicodedata
from collections import defaultdict


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c)).upper()


def channel_family(name):
    value = re.sub(r'\s*\[[^\]]*\]$', '', fold(name))
    value = re.sub(r'\s*\((?:ALTERNATIVA \d+|BACKUP)\)', '', value)
    value = re.sub(r'\b(?:UHD|FHD|HD|SD|4K)\b', '', value)
    value = re.sub(r'\s+', ' ', value).strip()
    aliases = {'RTP ACORES':'RTP Açores', 'RTP AFRICA':'RTP África', 'RTP MEMORIA':'RTP Memória',
               'RTP NOTICIAS':'RTP Notícias', 'SIC NOTICIAS':'SIC Notícias', 'TVI FIC':'TVI Ficção',
               'TVI FICCAO':'TVI Ficção', 'CM TV':'CMTV', 'BTV (BENFICA)':'Benfica TV',
               'BTV':'Benfica TV', 'BENFICA TV':'Benfica TV', 'CINE MUNDO':'Cinemundo',
               'CINEMUNDO':'Cinemundo', 'AR TV':'ARTV', 'AFRO MUSIC CHANNEL':'Afro Music',
               'NAT GEO':'National Geographic', 'NATIONAL GEOGRAPHIC':'National Geographic',
               'NAT GEO WILD':'National Geographic Wild', 'NICK JUNIOR':'Nick Jr.', 'NICK JR.':'Nick Jr.',
               'JIM JAM':'JimJam', 'JIMJAM':'JimJam', 'PANDA BIGGS':'Biggs', 'BIGGS':'Biggs',
               'MOTORVISION TV':'Motorvision', 'E! ENTERTAINMENT':'E!', 'SYFY PORTUGAL':'SYFY',
               'CRIME INVISTIGATION':'Crime + Investigation', 'CRIME+ INVESTIGATION':'Crime + Investigation',
               'TV RECORD':'Record TV', 'TOROS TV':'Toros', 'CAMPO PEQUENO TV':'Campo Pequeno'}
    if value in aliases:
        return aliases[value]
    match = re.fullmatch(r'ELEVEN SPORTS? (\d+)', value)
    if match:
        return 'DAZN ' + match[1]
    if value == 'SPORT TV':
        return 'Sport TV 1'
    match = re.fullmatch(r'RTP (\d+)', value)
    if match:
        return 'RTP ' + match[1]
    exact = {'SIC':'SIC', 'TVI':'TVI', 'V+ TVI':'V+ TVI', 'ARTV':'ARTV', 'CMTV':'CMTV', 'RTP MADEIRA':'RTP Madeira',
             'SIC INTERNACIONAL':'SIC Internacional', 'CNN PORTUGAL':'CNN Portugal', 'TVI 24':'TVI 24',
             'EURONEWS':'Euronews', 'NEWS NOW':'News Now', 'PORTO CANAL':'Porto Canal'}
    if value in exact:
        return exact[value]
    if value.startswith('SPORT TV'):
        return value.replace('SPORT TV','Sport TV',1)
    if value.startswith('DAZN'):
        return value
    keep = {'AMC','AXN','SYFY','MTV','TV','HBO','NBA','PFC','TLC','HGTV','TCV','NOS','SIC','RTP'}
    return ' '.join(word if word in keep or any(c.isdigit() for c in word) else word.capitalize() for word in value.split())


def channel_category(family):
    name = fold(family)
    if name in {'RTP 1','RTP 2','SIC','TVI','RTP ACORES','RTP MADEIRA','RTP MEMORIA','RTP AFRICA',
                'SIC INTERNACIONAL','V+ TVI','PORTO CANAL','LOCAL VISAO','TCV INTERNACIONAL','STV NOTICIAS','ZAP VIVA'}:
        return 1, '01 - Generalistas e regionais'
    if name in {'RTP 3','RTP NOTICIAS','SIC NOTICIAS','CNN PORTUGAL','CMTV','NEWS NOW','TVI 24','EURONEWS','BLOOMBERG','CNBC','ARTV'}:
        return 2, '02 - Notícias'
    if name.startswith(('SPORT TV','DAZN','EUROSPORT')) or name in {'BENFICA TV','SPORTING TV','CANAL 11','A BOLA TV','FUEL TV','PFC','NBA TV','MOTORVISION','MOTO GP','W-SPORT','FIGHT NETWORK','KOMBAT SPORT','COMBATE','NAUTICAL CHANNEL','TOROS','CAMPO PEQUENO','CACAVISION','CACCIA E PESCA','CAZA Y PESCA'}:
        return 3, '03 - Desporto'
    if name.startswith(('AXN','AMC','STAR','FOX','TVCINE','HBO')) or name in {'HOLLYWOOD','CINEMUNDO','SYFY','DIZI CHANNEL','NOS STUDIOS','DISNEY+ PIXAR'}:
        return 4, '04 - Filmes e séries'
    if name.startswith(('PANDA','DISNEY','NICKELODEON','NICK JR','CARTOON')) or name in {'BABY TV','BIGGS','JIMJAM','KANUCA TV','KURIAKOS KIDS','FIREMAN SAM','PATRULHA PATA','SANTIAGO DOS MARES','CANAL PANDA','SIC K'}:
        return 5, '05 - Infantil'
    if name.startswith(('DISCOVERY','NATIONAL GEOGRAPHIC','CRIME','INVESTIGATION')) or name in {'HISTORIA','ODISSEIA','BLAZE','CBS REALITY'}:
        return 6, '06 - Documentários'
    if name.startswith(('MTV','MCM','MEZZO','STINGRAY','TRACE','VH1','AFRO MUSIC')) or name in {'ALMA LUSA','BOM SOM CHANNEL'}:
        return 7, '07 - Música'
    if name in {'CANCAO NOVA','FATIMA TV','KURIAKOS TV','TV MANA 1','TV MANA 2','UNIFE TV'}:
        return 9, '09 - Religião'
    return 8, '08 - Entretenimento e lifestyle'


def natural(value):
    return tuple((0,int(p)) if p.isdigit() else (1,p) for p in re.split(r'(\d+)', fold(value)))


def organize(entries):
    """Group versions without dropping or changing any stream URL."""
    groups = defaultdict(list)
    for position in range(0,len(entries),2):
        header,url=entries[position:position+2]
        attrs,name=header.split(',',1)
        family=channel_family(name)
        quality=next((q for q in ('4K','UHD','FHD','HD','SD') if re.search(r'\b'+q+r'\b',name.upper())), '')
        backup='BACKUP' in name.upper()
        unavailable='Sem resposta' in attrs or 'tvg-source-status=' in attrs
        if unavailable and 'tvg-source-status=' not in attrs:
            attrs += ' tvg-source-status="unavailable"'
        groups[family].append((unavailable,backup,-{'4K':5,'UHD':4,'FHD':3,'HD':2,'SD':1}.get(quality,0),position,attrs,url,quality))
    first=['RTP 1','RTP 2','SIC','TVI','RTP 3','RTP Notícias','SIC Notícias','CNN Portugal','CMTV','News Now','Sport TV 1','Sport TV 2','Sport TV 3','Sport TV 4','Sport TV 5','Sport TV 6','Sport TV 7','Sport TV +','Sport TV NBA','DAZN 1','DAZN 2','DAZN 3','DAZN 4','DAZN 5','DAZN 6','Eurosport 1','Eurosport 2','Benfica TV','Sporting TV','Canal 11']
    ordered=sorted(groups,key=lambda f:(channel_category(f)[0],first.index(f) if f in first else 1000,natural(f)))
    output=[]
    for family in ordered:
        category=channel_category(family)[1]
        for number,(_,backup,_,_,attrs,url,quality) in enumerate(sorted(groups[family]),1):
            attrs=re.sub(r'\s+group-title="[^"]*"','',attrs)
            details=[quality] if quality else []
            if number>1:details.append('alternativa '+str(number))
            if backup:details.append('backup')
            display=family+(' ['+'; '.join(details)+']' if details else '')
            output.extend([attrs+' group-title="'+category+'",'+display,url])
    return output



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
    entries = organize(entries)
    target = Path(args.saida)
    temporary = target.with_suffix('.tmp')
    temporary.write_text('#EXTM3U\n' + '\n'.join(entries) + '\n', encoding='utf-8')
    temporary.replace(target)
    print(f'Criado: {target} ({len(entries)//2} entradas)', flush=True)


if __name__ == '__main__':
    main()


