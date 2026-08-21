FROM public.ecr.aws/lambda/python:3.11

# Install dependencies
RUN pip install --no-cache-dir gspread google-auth

# Copy application code
COPY src/ig_threads_telebot/ ${LAMBDA_TASK_ROOT}/ig_threads_telebot/

# Lambda handler
CMD ["ig_threads_telebot.handler.lambda_handler"]
