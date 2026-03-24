for f in /home/wrf/IMC/data/indice_*.geojson; do
  npx mapshaper@0.5.83 "$f" -simplify 10% keep-shapes -o "${f%.geojson}_light.geojson"
done
