# The image we are basing our image on
# Pinada por digest: a tag 3.13 é móvel, e uma base que muda sob os pés torna
# qualquer build irreproduzível por definição. Para atualizar a base: docker pull
# public.ecr.aws/lambda/python:3.13, copiar o novo RepoDigest para cá.
FROM public.ecr.aws/lambda/python:3.13@sha256:650b44d1a307d4c01e7dbba3879eb5251979844db991789b19a384041a3d508d

# Copy our requirements.txt file
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install dependencies
RUN pip install -r requirements.txt

# Copy all our python code
COPY src/* ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler, it is filename.function
CMD ["main.handler"]