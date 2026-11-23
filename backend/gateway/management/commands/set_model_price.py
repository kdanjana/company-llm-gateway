"""Allow a model on the gateway and set its price (USD per 1,000 tokens), from the AWS Bedrock pricing page.

    python manage.py set_model_price <model id> --input 0.001 --output 0.005 [--fallback <other model id>]

Running it again for the same model updates it. (Admins can also do this in the dashboard.)
"""
import argparse
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from gateway.models import ModelPrice


def usd(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"'{value}' is not a number")
    if amount < 0:
        raise argparse.ArgumentTypeError("price cannot be negative")
    return amount


class Command(BaseCommand):
    help = "Allow a model on the gateway and set its price per 1,000 tokens (USD)."

    def add_arguments(self, parser):
        parser.add_argument("model_id", help="Bedrock model ID or inference profile ID")
        parser.add_argument("--input", type=usd, required=True, help="USD per 1,000 input tokens")
        parser.add_argument("--output", type=usd, required=True, help="USD per 1,000 output tokens")
        parser.add_argument("--fallback", default=None, help="Model to retry on when this one is busy/unavailable")

    def handle(self, *args, **options):
        fallback = options["fallback"]
        if fallback is not None:
            if fallback == options["model_id"]:
                raise CommandError("A model cannot be its own fallback.")
            if not ModelPrice.objects.filter(model_id=fallback).exists():
                raise CommandError(f"Add the fallback model '{fallback}' with its price first.")

        defaults = {"input_price_per_1k": options["input"], "output_price_per_1k": options["output"], "is_enabled": True}
        if fallback is not None:
            defaults["fallback_model_id"] = fallback
        price, created = ModelPrice.objects.update_or_create(model_id=options["model_id"], defaults=defaults)

        action = "Added" if created else "Updated"
        extra = f", fallback: {price.fallback_model_id}" if price.fallback_model_id else ""
        self.stdout.write(self.style.SUCCESS(
            f"{action} {price.model_id}: input ${price.input_price_per_1k}/1k, output ${price.output_price_per_1k}/1k{extra}"
        ))
