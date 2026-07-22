resource "aws_security_group" "instance" {
  # name_prefix + create_before_destroy: a fixed name collides with itself on replacement.
  name_prefix = "${var.project}-instance-"
  description = "80/443 in, all out. No 22, access is Session Manager"
  vpc_id      = data.aws_vpc.default.id

  lifecycle {
    create_before_destroy = true
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.al2023_arm64.value
  instance_type          = "t4g.small"
  subnet_id              = sort(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.instance.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  # First-boot only; changing it recreates the box (fine — the box is ephemeral). See D-016.
  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    account         = data.aws_caller_identity.current.account_id
    region          = var.region
    compose_version = var.compose_plugin_version
    owner           = var.github_owner
    repo            = var.github_repo
  })

  metadata_options {
    http_tokens = "required"
    # 2, not 1: a container is a hop from the host and needs IMDS. See DECISIONS D-015.
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
  }

  # A new AL2023 release must not propose replacing a running box on an unrelated apply.
  lifecycle {
    ignore_changes = [ami]
  }

  tags = {
    Name = "${var.project}-app"
  }
}

resource "aws_eip" "app" {
  domain = "vpc"
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}
