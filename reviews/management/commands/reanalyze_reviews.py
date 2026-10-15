from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from reviews.models import tbl_review
from reviews.sentiment import analyze_feedback, SentimentUnavailable


class Command(BaseCommand):
    help = 'Reanalyze legacy reviews with missing model provenance. Dry run unless --apply is given.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--review-id', action='append', default=[])
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        if not 1 <= options['limit'] <= 1000:
            raise CommandError('Limit must be between 1 and 1000.')
        reviews = tbl_review.objects.filter(sentiment_analysis={}).order_by('createdAt')
        if options['review_id']:
            reviews = reviews.filter(pk__in=options['review_id'])
        saved, failed = 0, 0
        for review in list(reviews[:options['limit']]):
            try:
                analysis = analyze_feedback(review.unstructured_feedback)
            except SentimentUnavailable:
                failed += 1
                self.stderr.write(f'{review.pk}: unavailable; existing label retained')
                continue
            self.stdout.write(f'{review.pk}: {review.nlp_sentiment} -> {analysis["label"]}')
            if options['apply']:
                with transaction.atomic():
                    current = tbl_review.objects.select_for_update().get(pk=review.pk)
                    if current.sentiment_analysis or current.unstructured_feedback != review.unstructured_feedback:
                        self.stderr.write(f'{review.pk}: changed during analysis; skipped')
                        continue
                    analysis = dict(analysis, legacy_label=current.nlp_sentiment)
                    current.nlp_sentiment = analysis['label']
                    current.sentiment_analysis = analysis
                    current.save(update_fields=['nlp_sentiment', 'sentiment_analysis'])
                    saved += 1
        self.stdout.write(f'{"Applied" if options["apply"] else "Dry run"}: {saved} saved, {failed} unavailable.')
