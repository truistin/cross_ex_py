tag=$1
echo "docker-version:$tag"
image_name="ceff/cryptobridge-py:$tag"
docker build --network=host -t "$image_name" -f ./docker/Dockerfile .
docker push "$image_name"
echo "image $image_name -> push done"