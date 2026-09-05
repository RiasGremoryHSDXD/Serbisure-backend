from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.exceptions import Throttled, ValidationError, NotFound, PermissionDenied
from core.utils import check_valid_uuid
from rest_framework import status
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.views import APIView
from .serializers import (
    BookingSerializer,
    BookingFeedSerializer,
    BookingDetailSerializer,
    BookingProposalSerializer
)
from .models import tbl_booking, tbl_booking_assignment, tbl_booking_proposal
from django.core.cache import cache
from django.db.models import Q, Avg
from decimal import Decimal, InvalidOperation
from django.contrib.auth import get_user_model
from notifications.services import send_in_app_notification
import math 

User = get_user_model()


class BookingThrottle(UserRateThrottle):
    rate = '50/d'


class BookingView(generics.CreateAPIView):
    throttle_classes = [BookingThrottle]
    serializer_class = BookingSerializer
    queryset = tbl_booking.objects.all()
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if request.user.verification_status != "Verified":
            return Response({
                "detail": "Only verified user can post"},
                status=status.HTTP_403_FORBIDDEN
            )

        idempotency_key = request.headers.get('Idempotency-Key')
        if not idempotency_key or not check_valid_uuid(idempotency_key):
            return Response({"detail": "The Idempotency-Key header is required and must be a valid UUID v4."},
                            status=status.HTTP_400_BAD_REQUEST)

        cached_response = cache.get(idempotency_key)
        if cached_response:
            return Response(cached_response['data'], status=cached_response['status'])
        
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            booking = serializer.save(poster_id=request.user)

            response_data = {
                "message": "Booking posted successfully",
                "data": BookingDetailSerializer(booking, context={'request': request}).data
            }
            response_status = status.HTTP_201_CREATED

            if idempotency_key:
                cache.set(
                    idempotency_key,
                    {'data': response_data, 'status': response_status},
                    timeout=86400
                )

            return Response(response_data, status=response_status)

        return super().create(request, *args, **kwargs)
    
    def throttled(self, request, wait):
        if wait > 3600:
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."
        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait / 60)} minutes"
        raise Throttled(detail=custom_message)


class BookingFeedView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingFeedSerializer

    def get_queryset(self):
        current_user = self.request.user
        queryset = tbl_booking.objects.select_related('poster_id').filter(booking_status='Pending')

        if current_user.account_type == 'Homeowner':
            queryset = queryset.filter(poster_id__account_type='Kasambahay')
        elif current_user.account_type == 'Kasambahay':
            queryset = queryset.filter(poster_id__account_type='Homeowner')

        params = self.request.query_params

        # 1. Service Category filter
        category_param = params.get('category')
        if category_param:
            raw_cats = [c.strip() for c in category_param.split(',') if c.strip()]
            if raw_cats and 'All' not in raw_cats and 'all' not in raw_cats:
                cat_map = {
                    'cleaning': 'Cleaning',
                    'child_care': 'Child_care',
                    'child care': 'Child_care',
                    'cooking': 'Cooking',
                    'caregiver': 'Caregiver',
                    'laundry': 'Laundry',
                    'all-around': 'All-around',
                    'all around': 'All-around',
                }
                mapped_cats = [cat_map.get(c.lower(), c) for c in raw_cats]
                try:
                    queryset = queryset.filter(service_category__overlap=mapped_cats)
                except Exception:
                    cat_q = Q()
                    for cat in mapped_cats:
                        cat_q |= Q(service_category__icontains=cat)
                    queryset = queryset.filter(cat_q)

        # 2. Booking type filter
        bt_param = params.get('booking_type')
        if bt_param:
            bt_norm = bt_param.lower().replace('-', '_').strip()
            if bt_norm in ['short_term', 'part_time', 'parttime']:
                queryset = queryset.filter(booking_type='short_term')
            elif bt_norm in ['long_term', 'stay_in', 'stayin']:
                queryset = queryset.filter(booking_type='long_term')

        # 3. Max & Min daily rate
        max_rate = params.get('max_rate')
        if max_rate:
            try:
                queryset = queryset.filter(daily_rate__lte=Decimal(str(max_rate)))
            except (InvalidOperation, ValueError, TypeError):
                pass

        min_rate = params.get('min_rate')
        if min_rate:
            try:
                queryset = queryset.filter(daily_rate__gte=Decimal(str(min_rate)))
            except (InvalidOperation, ValueError, TypeError):
                pass

        # 4. Location filter
        location = params.get('location')
        if location and location.strip():
            queryset = queryset.filter(service_address__icontains=location.strip())

        # 5. Search keyword
        search_kw = params.get('search') or params.get('q')
        if search_kw and search_kw.strip():
            kw = search_kw.strip()
            queryset = queryset.filter(
                Q(service_address__icontains=kw) |
                Q(special_instruction__icontains=kw) |
                Q(poster_id__first_name__icontains=kw) |
                Q(poster_id__last_name__icontains=kw)
            )

        # 6. Sorting
        sort = params.get('sort', 'newest')
        if sort == 'rate_asc':
            queryset = queryset.order_by('daily_rate')
        elif sort == 'rate_desc':
            queryset = queryset.order_by('-daily_rate')
        elif sort == 'oldest':
            queryset = queryset.order_by('createdAt')
        else:
            queryset = queryset.order_by('-createdAt')

        return queryset


class BookingDetailView(generics.RetrieveAPIView):
    """
    Retrieve full details of a specific booking by UUID (Tier 1-1).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = BookingDetailSerializer
    queryset = tbl_booking.objects.select_related('poster_id').all()
    lookup_field = 'booking_id'


class BookingAcceptView(APIView):
    """
    Accepts a pending booking (Tier 1-1).
    - Can be accepted by the opposite party (e.g. Kasambahay accepting Homeowner's post).
    - Sets booking_status to 'Accepted'.
    - Creates or updates tbl_booking_assignment.
    - Sends an in-app notification to the poster.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, booking_id):
        try:
            booking = tbl_booking.objects.get(booking_id=booking_id)
        except tbl_booking.DoesNotExist:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        if booking.poster_id == request.user:
            return Response({'error': 'You cannot accept your own booking.'}, status=status.HTTP_400_BAD_REQUEST)

        if booking.booking_status != 'Pending':
            return Response({'error': f'Booking cannot be accepted because it is already {booking.booking_status}.'},
                            status=status.HTTP_400_BAD_REQUEST)

        booking.booking_status = 'Accepted'
        booking.save(update_fields=['booking_status'])

        assignment, _ = tbl_booking_assignment.objects.get_or_create(
            booking_id=booking,
            defaults={'accepter_id': request.user}
        )
        if assignment.accepter_id != request.user:
            assignment.accepter_id = request.user
            assignment.save(update_fields=['accepter_id'])

        # Send in-app notification to the poster
        accepter_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        cats = ", ".join(booking.service_category) if isinstance(booking.service_category, list) else str(booking.service_category)
        send_in_app_notification(
            receiver=booking.poster_id,
            sender=request.user,
            message=f"{accepter_name} has accepted your booking request for {cats}!"
        )

        return Response({
            'message': 'Booking accepted successfully.',
            'booking': BookingDetailSerializer(booking, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class BookingStartView(APIView):
    """
    Marks an 'Accepted' booking as 'InProgress' (Tier 1-1).
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, booking_id):
        try:
            booking = tbl_booking.objects.get(booking_id=booking_id)
        except tbl_booking.DoesNotExist:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        assignment = booking.assignments.select_related('accepter_id').first()
        is_accepter = assignment and assignment.accepter_id == request.user
        is_poster = booking.poster_id == request.user

        if not (is_poster or is_accepter):
            return Response({'error': 'You are not authorized to update this booking.'}, status=status.HTTP_403_FORBIDDEN)

        if booking.booking_status != 'Accepted':
            return Response({'error': f'Booking must be in Accepted status to start. Current: {booking.booking_status}.'},
                            status=status.HTTP_400_BAD_REQUEST)

        booking.booking_status = 'InProgress'
        booking.save(update_fields=['booking_status'])

        # Notify counterparty
        counterparty = assignment.accepter_id if is_poster and assignment else booking.poster_id
        actor_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        cats = ", ".join(booking.service_category) if isinstance(booking.service_category, list) else str(booking.service_category)
        send_in_app_notification(
            receiver=counterparty,
            sender=request.user,
            message=f"{actor_name} marked the {cats} job as In Progress."
        )

        return Response({
            'message': 'Booking is now In Progress.',
            'booking': BookingDetailSerializer(booking, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class BookingCompleteView(APIView):
    """
    Marks a booking as 'Completed' (Tier 1-1).
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, booking_id):
        try:
            booking = tbl_booking.objects.get(booking_id=booking_id)
        except tbl_booking.DoesNotExist:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        assignment = booking.assignments.select_related('accepter_id').first()
        is_accepter = assignment and assignment.accepter_id == request.user
        is_poster = booking.poster_id == request.user

        if not (is_poster or is_accepter):
            return Response({'error': 'You are not authorized to complete this booking.'}, status=status.HTTP_403_FORBIDDEN)

        if booking.booking_status not in ['InProgress', 'Accepted']:
            return Response({'error': f'Booking cannot be completed from {booking.booking_status} status.'},
                            status=status.HTTP_400_BAD_REQUEST)

        booking.booking_status = 'Completed'
        booking.save(update_fields=['booking_status'])

        # Notify counterparty and encourage review
        counterparty = assignment.accepter_id if is_poster and assignment else booking.poster_id
        cats = ", ".join(booking.service_category) if isinstance(booking.service_category, list) else str(booking.service_category)
        send_in_app_notification(
            receiver=counterparty,
            sender=request.user,
            message=f"Job for {cats} is marked as Completed! Please share your feedback and leave a review."
        )

        return Response({
            'message': 'Booking marked as Completed.',
            'booking': BookingDetailSerializer(booking, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class BookingCancelView(APIView):
    """
    Cancels a booking (Tier 1-1).
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, booking_id):
        try:
            booking = tbl_booking.objects.get(booking_id=booking_id)
        except tbl_booking.DoesNotExist:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        assignment = booking.assignments.select_related('accepter_id').first()
        is_accepter = assignment and assignment.accepter_id == request.user
        is_poster = booking.poster_id == request.user

        if not (is_poster or is_accepter):
            return Response({'error': 'You are not authorized to cancel this booking.'}, status=status.HTTP_403_FORBIDDEN)

        if booking.booking_status in ['Completed', 'Cancelled']:
            return Response({'error': f'Booking is already {booking.booking_status}.'}, status=status.HTTP_400_BAD_REQUEST)

        booking.booking_status = 'Cancelled'
        booking.save(update_fields=['booking_status'])

        # Notify counterparty if assignment existed
        if assignment and assignment.accepter_id:
            counterparty = assignment.accepter_id if is_poster else booking.poster_id
            actor_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
            cats = ", ".join(booking.service_category) if isinstance(booking.service_category, list) else str(booking.service_category)
            send_in_app_notification(
                receiver=counterparty,
                sender=request.user,
                message=f"Booking for {cats} was cancelled by {actor_name}."
            )

        return Response({
            'message': 'Booking has been cancelled.',
            'booking': BookingDetailSerializer(booking, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class MyBookingsView(generics.ListAPIView):
    """
    List all bookings posted by the authenticated user (Tier 1-4).
    Query param ?status=Active|Completed|Cancelled (where Active = Pending, Accepted, InProgress).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = BookingDetailSerializer

    def get_queryset(self):
        user = self.request.user
        qs = tbl_booking.objects.filter(poster_id=user).select_related('poster_id').order_by('-createdAt')

        status_param = self.request.query_params.get('status', '').strip().lower()
        if status_param == 'active':
            qs = qs.filter(booking_status__in=['Pending', 'Accepted', 'InProgress'])
        elif status_param == 'completed':
            qs = qs.filter(booking_status='Completed')
        elif status_param == 'cancelled':
            qs = qs.filter(booking_status='Cancelled')
        elif status_param:
            qs = qs.filter(booking_status__iexact=status_param)

        return qs


class MyAssignedBookingsView(generics.ListAPIView):
    """
    List all bookings where the authenticated user is the assigned worker (Tier 1-4).
    Query param ?status=Active|Completed|Cancelled.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = BookingDetailSerializer

    def get_queryset(self):
        user = self.request.user
        qs = tbl_booking.objects.filter(
            assignments__accepter_id=user
        ).select_related('poster_id').order_by('-createdAt')

        status_param = self.request.query_params.get('status', '').strip().lower()
        if status_param == 'active':
            qs = qs.filter(booking_status__in=['Pending', 'Accepted', 'InProgress'])
        elif status_param == 'completed':
            qs = qs.filter(booking_status='Completed')
        elif status_param == 'cancelled':
            qs = qs.filter(booking_status='Cancelled')
        elif status_param:
            qs = qs.filter(booking_status__iexact=status_param)

        return qs


class BookingProposalCreateView(APIView):
    """
    Submit a counter-offer / proposal for a booking (Tier 2-1).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
        try:
            booking = tbl_booking.objects.get(booking_id=booking_id)
        except tbl_booking.DoesNotExist:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        if booking.poster_id == request.user:
            return Response({'error': 'You cannot make a proposal on your own booking.'}, status=status.HTTP_400_BAD_REQUEST)

        if booking.booking_status != 'Pending':
            return Response({'error': 'Proposals can only be submitted for Pending bookings.'}, status=status.HTTP_400_BAD_REQUEST)

        proposed_rate = request.data.get('proposed_rate')
        message = request.data.get('message', '')

        if not proposed_rate:
            return Response({'error': 'Proposed rate is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rate_val = Decimal(str(proposed_rate))
            if rate_val < Decimal('1.00'):
                raise ValueError
        except Exception:
            return Response({'error': 'Proposed rate must be a valid amount of at least 1.00.'}, status=status.HTTP_400_BAD_REQUEST)

        proposal = tbl_booking_proposal.objects.create(
            booking_id=booking,
            proposer_id=request.user,
            proposed_rate=rate_val,
            message=message
        )

        # Notify poster
        proposer_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        send_in_app_notification(
            receiver=booking.poster_id,
            sender=request.user,
            message=f"{proposer_name} offered a counter-rate of P{rate_val} for your booking."
        )

        return Response({
            'message': 'Proposal submitted successfully.',
            'proposal': BookingProposalSerializer(proposal).data
        }, status=status.HTTP_201_CREATED)


class BookingProposalListView(generics.ListAPIView):
    """
    List all proposals for a booking (Tier 2-1).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = BookingProposalSerializer

    def get_queryset(self):
        booking_id = self.kwargs.get('booking_id')
        user = self.request.user

        try:
            booking = tbl_booking.objects.get(booking_id=booking_id)
        except tbl_booking.DoesNotExist:
            return tbl_booking_proposal.objects.none()

        # If user is poster, they see all proposals; otherwise, only their own
        if booking.poster_id == user:
            return tbl_booking_proposal.objects.filter(booking_id=booking).select_related('proposer_id').order_by('-createdAt')
        else:
            return tbl_booking_proposal.objects.filter(booking_id=booking, proposer_id=user).select_related('proposer_id').order_by('-createdAt')


class BookingProposalRespondView(APIView):
    """
    Poster accepts or rejects a counter-offer proposal (Tier 2-1).
    If accepted:
      - proposal.status = 'Accepted'
      - booking.daily_rate = proposal.proposed_rate
      - booking.booking_status = 'Accepted'
      - creates tbl_booking_assignment with accepter_id = proposal.proposer_id
      - rejects other pending proposals
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, proposal_id):
        try:
            proposal = tbl_booking_proposal.objects.select_related('booking_id', 'proposer_id').get(proposal_id=proposal_id)
        except tbl_booking_proposal.DoesNotExist:
            return Response({'error': 'Proposal not found.'}, status=status.HTTP_404_NOT_FOUND)

        booking = proposal.booking_id
        if booking.poster_id != request.user:
            return Response({'error': 'Only the booking creator can respond to proposals.'}, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get('action', '').strip().lower()
        if action not in ['accept', 'reject']:
            return Response({'error': "Action must be either 'accept' or 'reject'."}, status=status.HTTP_400_BAD_REQUEST)

        if proposal.status != 'Pending':
            return Response({'error': f'Proposal has already been {proposal.status}.'}, status=status.HTTP_400_BAD_REQUEST)

        if action == 'accept':
            proposal.status = 'Accepted'
            proposal.save(update_fields=['status'])

            booking.daily_rate = proposal.proposed_rate
            booking.booking_status = 'Accepted'
            booking.save(update_fields=['daily_rate', 'booking_status'])

            tbl_booking_assignment.objects.update_or_create(
                booking_id=booking,
                defaults={'accepter_id': proposal.proposer_id}
            )

            # Reject all other pending proposals for this booking
            tbl_booking_proposal.objects.filter(booking_id=booking, status='Pending').exclude(proposal_id=proposal.proposal_id).update(status='Rejected')

            # Notify proposer
            poster_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
            send_in_app_notification(
                receiver=proposal.proposer_id,
                sender=request.user,
                message=f"{poster_name} accepted your offer of P{proposal.proposed_rate}! The booking is now confirmed."
            )

            return Response({
                'message': 'Proposal accepted and booking confirmed.',
                'proposal': BookingProposalSerializer(proposal).data,
                'booking': BookingDetailSerializer(booking, context={'request': request}).data
            }, status=status.HTTP_200_OK)
        else:
            proposal.status = 'Rejected'
            proposal.save(update_fields=['status'])

            # Notify proposer
            send_in_app_notification(
                receiver=proposal.proposer_id,
                sender=request.user,
                message=f"Your counter-offer for booking was declined."
            )

            return Response({
                'message': 'Proposal rejected.',
                'proposal': BookingProposalSerializer(proposal).data
            }, status=status.HTTP_200_OK)


class BookingRecommendationsView(APIView):
    """
    Smart Matching / Recommendation Engine (Tier 3-2).
    - If user is Homeowner: Recommends top matching Kasambahay workers based on category match, rating, and location.
    - If user is Kasambahay: Recommends top matching open Job postings based on user's skills/tags and location.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        recommendations = []

        if user.account_type == 'Homeowner':
            # Recommend workers
            workers = User.objects.filter(account_type='Kasambahay', is_active=True).exclude(id=user.id)
            user_location = (user.city or user.province or '').lower()

            scored_workers = []
            for w in workers:
                score = 0
                # Location matching (+30)
                w_loc = (w.city or w.province or '').lower()
                if user_location and w_loc and (user_location in w_loc or w_loc in user_location):
                    score += 30

                # Rating matching (+0 to 40)
                avg_r = tbl_review.objects.filter(reviewee_id=w).aggregate(avg=Avg('rating'))['avg']
                rating_val = float(avg_r) if avg_r is not None else 4.0
                score += int(rating_val * 8)

                # Verification bonus (+20)
                if getattr(w, 'verification_status', None) == 'Verified':
                    score += 20

                # Has tags (+10)
                if w.user_tags and len(w.user_tags) > 0:
                    score += 10

                from .serializers import get_signed_avatar
                first = w.first_name or ''
                last = w.last_name or ''
                scored_workers.append({
                    'id': str(w.id),
                    'name': f"{first} {last}".strip() or w.username,
                    'role': 'Kasambahay',
                    'match_score': min(score, 100),
                    'rating': round(rating_val, 1),
                    'location': f"{w.city or ''}, {w.province or ''}".strip(', ') or 'Philippines',
                    'tags': w.user_tags or [],
                    'avatar': get_signed_avatar(w),
                    'verification_status': w.verification_status,
                })

            scored_workers.sort(key=lambda x: x['match_score'], reverse=True)
            recommendations = scored_workers[:15]

        else:
            # Kasambahay: Recommend open Pending jobs from Homeowners
            pending_jobs = tbl_booking.objects.filter(
                booking_status='Pending',
                poster_id__account_type='Homeowner'
            ).select_related('poster_id')

            user_tags = [t.lower() for t in (user.user_tags or [])]
            user_loc = (user.city or user.province or '').lower()

            scored_jobs = []
            for job in pending_jobs:
                score = 30  # base
                # Tag / Category overlap
                cats = [c.lower() for c in (job.service_category or [])]
                for cat in cats:
                    if any(t in cat or cat in t for t in user_tags):
                        score += 35
                        break

                # Location match
                if user_loc and user_loc in (job.service_address or '').lower():
                    score += 25

                # Fair rate bonus
                if job.daily_rate >= Decimal('500.00'):
                    score += 10

                from .serializers import get_signed_avatar
                p_first = job.poster_id.first_name or ''
                p_last = job.poster_id.last_name or ''
                scored_jobs.append({
                    'booking_id': str(job.booking_id),
                    'title': ", ".join(job.service_category) if isinstance(job.service_category, list) else str(job.service_category),
                    'daily_rate': str(job.daily_rate),
                    'location': job.service_address,
                    'match_score': min(score, 100),
                    'poster_name': f"{p_first} {p_last}".strip() or job.poster_id.username,
                    'poster_avatar': get_signed_avatar(job.poster_id),
                    'booking_type': job.booking_type,
                    'createdAt': str(job.createdAt),
                })

            scored_jobs.sort(key=lambda x: x['match_score'], reverse=True)
            recommendations = scored_jobs[:15]

        return Response({
            'recommendations': recommendations,
            'count': len(recommendations)
        }, status=status.HTTP_200_OK)