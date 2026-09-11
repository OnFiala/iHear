import {createRequire} from 'node:module';
import {dirname} from 'node:path';
const require=createRequire(import.meta.url);
const sharp=require(require.resolve('sharp',{paths:[dirname(require.resolve('next/package.json'))]}));
for(const [size,path] of [[192,'public/app-icon.png'],[512,'public/app-icon-512.png']])await sharp('public/icon.svg').resize(size,size).png().toFile(path);
console.log('Rendered original SVG app icons at 192 and 512 pixels.');
