# R6-minimal: WeasyPrint 69 uses pydyf + Pillow, so no cairo/gdk-pixbuf. See D-019.
FROM public.ecr.aws/lambda/python:3.13

RUN dnf install -y pango shared-mime-info dejavu-sans-fonts dejavu-serif-fonts \
 && dnf clean all && rm -rf /var/cache/dnf

ENV XDG_CACHE_HOME=/tmp FONTCONFIG_PATH=/var/task/fonts
COPY fonts/fonts.conf ${LAMBDA_TASK_ROOT}/fonts/
RUN fc-cache -f

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY handler.py ${LAMBDA_TASK_ROOT}/
CMD ["handler.handler"]
