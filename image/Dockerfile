# The image we are basing our image on
FROM public.ecr.aws/lambda/python:3.13

# Copy our requirements.txt file
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install dependencies
RUN pip install -r requirements.txt

# Copy all our python code
COPY src/* ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler, it is filename.function
CMD ["main.handler"]